#include <poll.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/syscall.h>
#include <time.h>

#define OWNED_MAX_TIDS 4096
#define OWNED_MAX_PACKET 65536

struct owned_tid {
	int tid;
	int tgid;
	bool held;
	unsigned int restart_op;
	unsigned int restart_sig;
};

struct owned_birth {
	int tid;
	int tgid;
	int creator_tid;
	int creator_tgid;
	unsigned int event;
	unsigned long ordinal;
	unsigned long long start_ticks;
	long long rss_pages;
	int kernel_ppid;
	unsigned long long boot_ns;
	unsigned int first_stop_status;
	unsigned int shared_vm;
	bool deferred_event;
	bool event_seen;
	bool stop_seen;
	bool acknowledged;
};

static int owned_socket = -1;
static bool owned_freezing;
static bool owned_held;
static bool owned_started;
static unsigned long owned_sequence;
static unsigned long owned_snapshot_id;
static bool owned_need_interrupt;
static bool owned_inject_child_first;
static bool owned_inject_drain_delay;
static bool owned_inject_drain_birth;
static bool owned_inject_event_failure;
static bool owned_inject_ack_failure;
static bool owned_inject_held_failure;
static bool owned_inject_resume_failure;
static volatile sig_atomic_t owned_wake;

static void
owned_wakeup(int signal_number)
{
	(void) signal_number;
	owned_wake = 1;
}
static struct owned_tid owned_tids[OWNED_MAX_TIDS];
static size_t owned_tid_count;
static struct owned_birth owned_births[OWNED_MAX_TIDS];
static size_t owned_birth_count;

static void
owned_fail(const char *reason)
{
	if (owned_socket >= 0) {
		char packet[256];
		int size = snprintf(packet, sizeof(packet), "ERROR %s\n", reason);
		if (size > 0 && (size_t) size < sizeof(packet))
			(void) send(owned_socket, packet, size, MSG_NOSIGNAL | MSG_DONTWAIT);
	}
	_exit(125);
}

static struct owned_tid *
owned_tid_row(int tid, bool create)
{
	for (size_t i = 0; i < owned_tid_count; ++i)
		if (owned_tids[i].tid == tid)
			return &owned_tids[i];
	if (!create)
		return NULL;
	if (owned_tid_count == OWNED_MAX_TIDS)
		owned_fail("TID_LIMIT");
	struct owned_tid *row = &owned_tids[owned_tid_count++];
	memset(row, 0, sizeof(*row));
	row->tid = tid;
	return row;
}

static struct owned_birth *
owned_birth_row(int tid, bool create)
{
	for (size_t i = 0; i < owned_birth_count; ++i)
		if (owned_births[i].tid == tid)
			return &owned_births[i];
	if (!create)
		return NULL;
	if (owned_birth_count == OWNED_MAX_TIDS)
		owned_fail("BIRTH_LIMIT");
	struct owned_birth *row = &owned_births[owned_birth_count++];
	memset(row, 0, sizeof(*row));
	row->tid = tid;
	return row;
}

static void
owned_proc(int tid, int *tgid, unsigned long long *start,
	   long long *rss, int *ppid)
{
	char path[64], line[8192];
	int fields_seen = 0;
	if (snprintf(path, sizeof(path), "/proc/%d/stat", tid) >= (int) sizeof(path))
		owned_fail("STAT_PATH");
	FILE *input = fopen(path, "r");
	if (!input || !fgets(line, sizeof(line), input) ||
	    !strchr(line, '\n') || fclose(input))
		owned_fail("STAT_READ");
	char *tail = strrchr(line, ')');
	if (!tail || tail[1] != ' ')
		owned_fail("STAT_PARSE");
	char *save = NULL;
	for (char *token = strtok_r(tail + 2, " \n", &save); token;
	     token = strtok_r(NULL, " \n", &save)) {
		int field = ++fields_seen + 2;
		if (field == 4 || field == 22 || field == 24) {
			char *end;
			errno = 0;
			if (field == 22) {
				unsigned long long value = strtoull(token, &end, 10);
				if (errno || *end || !value)
					owned_fail("START_PARSE");
				*start = value;
			} else {
				long long value = strtoll(token, &end, 10);
				if (errno || *end || value < 0 ||
				    (field == 4 && (value == 0 || value > INT_MAX)))
					owned_fail("STAT_NUMBER");
				if (field == 4)
					*ppid = (int) value;
				else
					*rss = value;
			}
		}
	}
	if (fields_seen < 22 || !*start || *rss < 0 || !*ppid)
		owned_fail("STAT_FIELDS");
	if (snprintf(path, sizeof(path), "/proc/%d/status", tid) >= (int) sizeof(path))
		owned_fail("STATUS_PATH");
	input = fopen(path, "r");
	if (!input)
		owned_fail("STATUS_OPEN");
	int found = 0;
	while (fgets(line, sizeof(line), input)) {
		if (strncmp(line, "Tgid:\t", 6) == 0) {
			char extra;
			if (sscanf(line + 6, "%d %c", tgid, &extra) != 1 || *tgid <= 0)
				owned_fail("TGID_PARSE");
			++found;
		}
	}
	if (ferror(input) || fclose(input) || found != 1)
		owned_fail("STATUS_READ");
}

static int
owned_pidfd(int pid)
{
	int handle = syscall(SYS_pidfd_open, pid, 0);
	if (handle < 0)
		owned_fail("PIDFD_OPEN");
	return handle;
}

static void owned_command(const char *packet);
static void owned_release_birth_holds(void);
static void owned_child_stop(int child_tid, int status);

static void
owned_send(const char *packet, int handle)
{
	struct iovec vector = {.iov_base = (void *) packet,
			       .iov_len = strlen(packet)};
	char control[CMSG_SPACE(sizeof(int))] = {0};
	struct msghdr message = {.msg_iov = &vector, .msg_iovlen = 1};
	if (handle >= 0) {
		message.msg_control = control;
		message.msg_controllen = sizeof(control);
		struct cmsghdr *header = CMSG_FIRSTHDR(&message);
		header->cmsg_level = SOL_SOCKET;
		header->cmsg_type = SCM_RIGHTS;
		header->cmsg_len = CMSG_LEN(sizeof(int));
		memcpy(CMSG_DATA(header), &handle, sizeof(handle));
	}
	if (sendmsg(owned_socket, &message, MSG_NOSIGNAL) != (ssize_t) vector.iov_len)
		owned_fail("EVENT_SEND");
	if (handle >= 0 && close(handle))
		owned_fail("PIDFD_CLOSE");
	if (owned_inject_ack_failure && !strncmp(packet, "BIRTH ", 6))
		owned_fail("ACK_READ");
	for (;;) {
		char reply[256];
		ssize_t size = recv(owned_socket, reply, sizeof(reply) - 1, 0);
		if (size < 0 && errno == EINTR)
			continue;
		if (size <= 0 || size == (ssize_t) sizeof(reply) - 1)
			owned_fail("ACK_READ");
		reply[size] = 0;
		char expected[64];
		snprintf(expected, sizeof(expected), "ACK %lu\n", owned_sequence);
		if (strcmp(reply, expected) == 0)
			return;
		owned_command(reply);
	}
}

static void
owned_record(const char *kind, const char *payload, int handle)
{
	char packet[OWNED_MAX_PACKET];
	++owned_sequence;
	int size = snprintf(packet, sizeof(packet), "%s %lu %s\n",
			    kind, owned_sequence, payload);
	if (size <= 0 || (size_t) size >= sizeof(packet))
		owned_fail("EVENT_LENGTH");
	owned_send(packet, handle);
}

static void
owned_join(struct owned_birth *birth)
{
	if (!birth->event_seen || !birth->stop_seen || birth->acknowledged)
		return;
	if (owned_inject_event_failure)
		owned_fail("EVENT_SEND");
	char payload[256];
	int size = snprintf(payload, sizeof(payload),
		"%lu %d %d %d %d %u %llu %lld %d %llu %u %u",
		birth->ordinal, birth->creator_tid, birth->creator_tgid,
		birth->tid, birth->tgid, birth->event, birth->start_ticks,
		birth->rss_pages, birth->kernel_ppid, birth->boot_ns,
		birth->first_stop_status, birth->shared_vm);
	if (size <= 0 || (size_t) size >= sizeof(payload))
		owned_fail("BIRTH_LENGTH");
	owned_record("BIRTH", payload,
		birth->tid == birth->tgid ? owned_pidfd(birth->tid) : -1);
	birth->acknowledged = true;
	if (!owned_freezing)
		owned_release_birth_holds();
}

static void
owned_birth_event(int creator_tid, unsigned int event, unsigned long child)
{
	if (!child || child > INT_MAX || child == (unsigned long) creator_tid)
		owned_fail("EVENT_CHILD");
	struct owned_birth *birth = owned_birth_row((int) child, true);
	if (birth->event_seen || birth->acknowledged)
		owned_fail("DUPLICATE_BIRTH");
	unsigned long long start = 0;
	long long rss = -1;
	int creator_tgid = 0, ppid = 0;
	owned_proc(creator_tid, &creator_tgid, &start, &rss, &ppid);
	birth->event_seen = !owned_inject_child_first;
	birth->deferred_event = owned_inject_child_first;
	birth->creator_tid = creator_tid;
	birth->creator_tgid = creator_tgid;
	birth->event = event;
	owned_inject_drain_birth = false;
	birth->shared_vm = event == PTRACE_EVENT_VFORK ? 1 :
			   event == PTRACE_EVENT_CLONE ? 2 : 0;
	birth->ordinal = 1;
	for (size_t i = 0; i < owned_birth_count; ++i)
		if (&owned_births[i] != birth && owned_births[i].event_seen &&
		    owned_births[i].creator_tid == creator_tid)
			++birth->ordinal;
	owned_join(birth);
}

static void
owned_child_stop(int child_tid, int status)
{
	struct owned_birth *birth = owned_birth_row(child_tid, true);
	if (birth->stop_seen || birth->acknowledged)
		owned_fail("DUPLICATE_CHILD_STOP");
	long long rss = -1;
	int ppid = 0;
	owned_proc(child_tid, &birth->tgid, &birth->start_ticks, &rss, &ppid);
	birth->rss_pages = rss;
	birth->kernel_ppid = ppid;
	struct timespec boot;
	if (clock_gettime(CLOCK_BOOTTIME, &boot) < 0)
		owned_fail("BOOT_CLOCK");
	birth->boot_ns = (unsigned long long) boot.tv_sec * 1000000000ULL + boot.tv_nsec;
	birth->first_stop_status = (unsigned int) status;
	if (birth->tgid != child_tid)
		birth->shared_vm = 1;
	birth->stop_seen = true;
	struct owned_tid *row = owned_tid_row(child_tid, true);
	row->tgid = birth->tgid;
	if (birth->deferred_event) {
		birth->event_seen = true;
		birth->deferred_event = false;
	}
	owned_join(birth);
}

static bool
owned_birth_pending(int tid)
{
	for (size_t i = 0; i < owned_birth_count; ++i)
		if (!owned_births[i].acknowledged &&
		    (owned_births[i].tid == tid ||
		     (owned_births[i].event_seen && owned_births[i].creator_tid == tid)))
			return true;
	return false;
}

static void
owned_exec(int current_tid, unsigned long former_tid)
{
	if (!former_tid || former_tid > INT_MAX)
		owned_fail("EXEC_EVENT");
	unsigned long long start = 0;
	long long rss = -1;
	int tgid = 0, ppid = 0;
	owned_proc(current_tid, &tgid, &start, &rss, &ppid);
	struct owned_tid *row = owned_tid_row(current_tid, true);
	row->tgid = tgid;
	if ((int) former_tid != current_tid) {
		struct owned_tid *old = owned_tid_row((int) former_tid, false);
		if (!old || old->tgid != tgid)
			owned_fail("EXEC_FORMER_ID");
		for (size_t i = 0; i < owned_tid_count; ++i)
			if (owned_tids[i].tid != current_tid &&
			    owned_tids[i].tgid == tgid)
				owned_tids[i].tid = 0;
	}
	char payload[128];
	snprintf(payload, sizeof(payload), "%d %lu %d %llu", current_tid,
		 former_tid, tgid, start);
	owned_record("EXEC", payload, owned_pidfd(current_tid));
}

static void
owned_exit(int tid, int status)
{
	struct owned_tid *row = owned_tid_row(tid, false);
	if (!row || owned_birth_pending(tid))
		owned_fail("EXIT_IDENTITY");
	char payload[96];
	snprintf(payload, sizeof(payload), "%d %d %d", tid, row->tgid, status);
	owned_record("EXIT", payload, -1);
	row->tid = 0;
}

static bool
owned_hold_restart(struct tcb *tcp, unsigned int op, unsigned int sig)
{
	if (owned_freezing && owned_inject_drain_birth &&
	    tcp->pid == strace_child) {
		return false;
	}
	struct owned_tid *row = owned_tid_row(tcp->pid, true);
	if (!row->tgid) {
		unsigned long long start = 0;
		long long rss = -1;
		int ppid = 0;
		owned_proc(tcp->pid, &row->tgid, &start, &rss, &ppid);
	}
	if (!owned_freezing && !owned_birth_pending(tcp->pid))
		return false;
	if (row->held)
		owned_fail("DUPLICATE_HOLD");
	row->held = true;
	row->restart_op = op;
	row->restart_sig = sig;
	return true;
}

static void
owned_after_restart(struct tcb *tcp)
{
	struct owned_tid *row = owned_tid_row(tcp->pid, true);
	row->held = false;
	owned_started = true;
}

static void
owned_interrupt_running(void)
{
	if (owned_inject_drain_delay) {
		owned_inject_drain_delay = false;
		struct timespec delay = {.tv_nsec = 60000000};
		while (nanosleep(&delay, &delay) < 0 && errno == EINTR)
			;
	}
	for (size_t i = 0; i < owned_tid_count; ++i) {
		struct owned_tid *row = &owned_tids[i];
		if (row->tid && !row->held &&
		    ptrace(PTRACE_INTERRUPT, row->tid, 0L, 0L) < 0 &&
		    errno != EIO && errno != ESRCH)
			owned_fail("INTERRUPT_FAILED");
	}
}

static void
owned_release_birth_holds(void)
{
	for (size_t i = 0; i < owned_tid_count; ++i) {
		struct owned_tid *row = &owned_tids[i];
		if (!row->tid || !row->held || owned_birth_pending(row->tid))
			continue;
		struct tcb *tcp = pid2tcb(row->tid);
		if (!tcp || ptrace_restart(row->restart_op, tcp,
					     row->restart_sig) < 0)
			owned_fail("BIRTH_RESUME_FAILED");
		row->held = false;
	}
}

static void
owned_resume(void)
{
	if (!owned_freezing || !owned_held)
		owned_fail("RESUME_STATE");
	if (owned_inject_resume_failure)
		owned_fail("RESUME_FAILED");
	for (size_t i = 0; i < owned_tid_count; ++i) {
		struct owned_tid *row = &owned_tids[i];
		if (!row->tid)
			continue;
		if (!row->held)
			owned_fail("RESUME_UNHELD");
		struct tcb *tcp = pid2tcb(row->tid);
		if (!tcp || ptrace_restart(row->restart_op, tcp,
					     row->restart_sig) < 0)
			owned_fail("RESUME_FAILED");
		row->held = false;
	}
	owned_freezing = false;
	owned_held = false;
	char payload[32];
	snprintf(payload, sizeof(payload), "%lu", owned_snapshot_id);
	owned_record("RESUMED", payload, -1);
}

static void
owned_command(const char *packet)
{
	unsigned long id = 0;
	char extra;
	if (sscanf(packet, "FREEZE %lu %c", &id, &extra) == 1 &&
	    id && !owned_freezing) {
		owned_snapshot_id = id;
		owned_freezing = true;
		owned_need_interrupt = true;
		return;
	}
	if (sscanf(packet, "RESUME %lu %c", &id, &extra) == 1 &&
	    id == owned_snapshot_id && owned_held) {
		owned_resume();
		return;
	}
	owned_fail("CONTROL_PACKET");
}

static void
owned_poll(int milliseconds)
{
	struct pollfd pollfd = {.fd = owned_socket, .events = POLLIN};
	int ready = poll(&pollfd, 1, milliseconds);
	if (ready < 0) {
		if (errno == EINTR)
			return;
		owned_fail("CONTROL_POLL");
	}
	if (!ready)
		return;
	if (pollfd.revents != POLLIN)
		owned_fail("CONTROL_CLOSED");
	char packet[256];
	ssize_t size = recv(owned_socket, packet, sizeof(packet) - 1,
			    MSG_DONTWAIT);
	if (size <= 0 || size == (ssize_t) sizeof(packet) - 1)
		owned_fail("CONTROL_READ");
	packet[size] = 0;
	owned_command(packet);
}

static void
owned_try_held(void)
{
	if (!owned_freezing || owned_held)
		return;
	for (size_t i = 0; i < owned_birth_count; ++i)
		if (!owned_births[i].acknowledged)
			return;
	if (owned_inject_held_failure)
		owned_fail("HELD_FAILED");
	char payload[OWNED_MAX_PACKET - 128];
	int size = snprintf(payload, sizeof(payload), "%lu", owned_snapshot_id);
	for (size_t i = 0; i < owned_tid_count; ++i) {
		struct owned_tid *row = &owned_tids[i];
		if (!row->tid)
			continue;
		if (!row->held)
			return;
		int written = snprintf(payload + size, sizeof(payload) - size,
				       " %d:%d", row->tid, row->tgid);
		if (written <= 0 || (size_t) written >= sizeof(payload) - size)
			owned_fail("HELD_LENGTH");
		size += written;
	}
	owned_record("HELD", payload, -1);
	owned_held = true;
}

static void
owned_init(void)
{
	const char *path = getenv("DYN4K_OWNED_SOCKET");
	if (!path)
		return;
	owned_inject_child_first = getenv("DYN4K_TEST_CHILD_FIRST") != NULL;
	owned_inject_drain_delay = getenv("DYN4K_TEST_DRAIN_DELAY") != NULL;
	owned_inject_drain_birth = getenv("DYN4K_TEST_DRAIN_BIRTH") != NULL;
	owned_inject_event_failure = getenv("DYN4K_TEST_EVENT_FAILURE") != NULL;
	owned_inject_ack_failure = getenv("DYN4K_TEST_ACK_FAILURE") != NULL;
	owned_inject_held_failure = getenv("DYN4K_TEST_HELD_FAILURE") != NULL;
	owned_inject_resume_failure = getenv("DYN4K_TEST_RESUME_FAILURE") != NULL;
	if (!use_seize || !followfork || nprocs != 1 || strace_child <= 0 ||
	    strlen(path) >= sizeof(((struct sockaddr_un *) 0)->sun_path))
		owned_fail("UNSUPPORTED_TRACER_MODE");
	owned_socket = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
	if (owned_socket < 0)
		owned_fail("SOCKET_OPEN");
	struct sockaddr_un address = {.sun_family = AF_UNIX};
	strcpy(address.sun_path, path);
	if (connect(owned_socket, (struct sockaddr *) &address,
		    sizeof(address)) < 0)
		owned_fail("SOCKET_CONNECT");
	set_sighandler(SIGUSR1, owned_wakeup, NULL);
	unsigned long long start = 0;
	long long rss = -1;
	int tgid = 0, ppid = 0;
	owned_proc(strace_child, &tgid, &start, &rss, &ppid);
	if (tgid != strace_child)
		owned_fail("ROOT_TGID");
	char payload[128];
	snprintf(payload, sizeof(payload), "%d %d %llu %lld",
		 strace_child, tgid, start, rss);
	owned_record("ROOT", payload, owned_pidfd(strace_child));
	struct owned_tid *row = owned_tid_row(strace_child, true);
	row->tgid = tgid;
}
