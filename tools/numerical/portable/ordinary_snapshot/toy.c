#define _GNU_SOURCE
#include <linux/sched.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static atomic_int exec_gate;

static void *thread_fork(void *unused)
{
	(void) unused;
	pid_t child = fork();
	if (child == 0) {
		execl("/bin/true", "true", (char *) NULL);
		_exit(127);
	}
	int status = 0;
	if (child < 0 || waitpid(child, &status, 0) != child || status)
		return (void *) 1;
	return NULL;
}

static void *thread_exec(void *hold)
{
	atomic_store_explicit(&exec_gate, 1, memory_order_release);
	while (atomic_load_explicit(&exec_gate, memory_order_acquire) != 2)
		sched_yield();
	if (hold)
		execl("/bin/sleep", "sleep", "0.2", (char *) NULL);
	else
		execl("/bin/true", "true", (char *) NULL);
	_exit(127);
}

int main(int argc, char **argv)
{
	if (argc != 2)
		return 2;
	if (!strcmp(argv[1], "nested")) {
		pthread_t thread;
		void *result = NULL;
		if (pthread_create(&thread, NULL, thread_fork, NULL) ||
		    pthread_join(thread, &result) || result)
			return 3;
		return 0;
	}
	if (!strcmp(argv[1], "nonleader") ||
	    !strcmp(argv[1], "nonleader_hold")) {
		pthread_t thread;
		if (pthread_create(&thread, NULL, thread_exec,
		    !strcmp(argv[1], "nonleader_hold") ? (void *) 1 : NULL))
			return 3;
		while (atomic_load_explicit(&exec_gate, memory_order_acquire) != 1)
			sched_yield();
		atomic_store_explicit(&exec_gate, 2, memory_order_release);
		pause();
		return 4;
	}
	pid_t child;
	if (!strcmp(argv[1], "vfork")) {
		child = vfork();
	} else if (!strcmp(argv[1], "clone3")) {
		struct clone_args args = {.exit_signal = SIGCHLD};
		child = syscall(SYS_clone3, &args, sizeof(args));
	} else if (!strcmp(argv[1], "untraced")) {
		child = syscall(SYS_clone, CLONE_UNTRACED | SIGCHLD,
				0, NULL, NULL, NULL);
	} else if (!strcmp(argv[1], "untraced_live")) {
		child = syscall(SYS_clone, CLONE_UNTRACED | SIGCHLD,
				0, NULL, NULL, NULL);
	} else if (!strcmp(argv[1], "freeze_birth")) {
		struct timespec start, now;
		clock_gettime(CLOCK_MONOTONIC, &start);
		do {
			clock_gettime(CLOCK_MONOTONIC, &now);
		} while ((now.tv_sec - start.tv_sec) * 1000000000LL +
		         now.tv_nsec - start.tv_nsec < 20000000LL);
		child = fork();
	} else if (!strcmp(argv[1], "fast") ||
		   !strcmp(argv[1], "group_escape") ||
		   !strcmp(argv[1], "parent_exit") ||
		   !strcmp(argv[1], "held_child") ||
		   !strcmp(argv[1], "drain_child")) {
		child = fork();
	} else {
		return 2;
	}
	if (child < 0)
		return 5;
	if (child == 0) {
		if (!strcmp(argv[1], "untraced"))
			_exit(0);
		if (!strcmp(argv[1], "untraced_live") ||
		    !strcmp(argv[1], "freeze_birth"))
			execl("/bin/sleep", "sleep", "0.3", (char *) NULL);
		if (!strcmp(argv[1], "group_escape") && setsid() < 0)
			_exit(6);
		if (!strcmp(argv[1], "held_child") ||
		    !strcmp(argv[1], "parent_exit"))
			execl("/bin/sleep", "sleep", "0.2", (char *) NULL);
		execl("/bin/true", "true", (char *) NULL);
		_exit(127);
	}
	if (!strcmp(argv[1], "parent_exit"))
		return 0;
	int status = 0;
	if (waitpid(child, &status, 0) != child || status)
		return 7;
	if (!strcmp(argv[1], "drain_child"))
		usleep(200000);
	return 0;
}
