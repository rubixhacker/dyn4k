(async () => {
    const parameters = new URL(self.location.href).searchParams;
    const token = parameters.get('token');
    const target = parameters.get('target');
    if (!token || !target || new URL(target).origin !== location.origin) {
        throw new Error('Safari witness bootstrap target differs');
    }
    const registration = await navigator.serviceWorker.register(
        '/__dyn4k_sw.js?token=' + encodeURIComponent(token), {scope: '/'});
    await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller) {
        await new Promise((resolve, reject) => {
            const timer = setTimeout(() => reject(new Error('Safari worker control timed out')), 15000);
            navigator.serviceWorker.addEventListener('controllerchange', () => {
                clearTimeout(timer);
                resolve();
            }, {once: true});
        });
    }
    if (registration.active !== navigator.serviceWorker.controller) {
        throw new Error('Safari worker did not control bootstrap');
    }
    const channel = new MessageChannel();
    const controlled = new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error('Safari worker handshake timed out')), 15000);
        channel.port1.onmessage = event => {
            clearTimeout(timer);
            resolve(event.data);
        };
    });
    navigator.serviceWorker.controller.postMessage({type: 'dyn4k-control', token},
        [channel.port2]);
    const answer = await controlled;
    if (answer.token !== token || !answer.client_id) {
        throw new Error('Safari worker handshake differs');
    }
    const recorded = await fetch('/__dyn4k_control', {
        method: 'POST', headers: {'content-type': 'application/json'},
        body: JSON.stringify({token, target, client_id: answer.client_id,
            bootstrap_url: location.href})
    });
    if (recorded.status !== 204) throw new Error('Safari control recording failed');
    location.replace(target);
})().catch(error => {
    document.body.textContent = 'Safari witness bootstrap failed: ' + String(error);
});
