import { useEffect, useState } from 'react';

let ready = false;
let started: Promise<void> | undefined;
const notify = () => {
  ready = true;
  window.dispatchEvent(new Event('crop-offline-ready'));
};

export function registerOfflineSupport(): Promise<void> {
  if (started) return started;
  started = (async () => {
    if (!('serviceWorker' in navigator) || !import.meta.env.PROD) return;
    navigator.serviceWorker.addEventListener('message', (event) => {
      if (event.data?.type === 'CROP_OFFLINE_READY') notify();
    });
    const registration = await navigator.serviceWorker.register(
      `${import.meta.env.BASE_URL}sw.js`,
      { scope: import.meta.env.BASE_URL },
    );
    const active = await navigator.serviceWorker.ready;
    (active.active || registration.active)?.postMessage({ type: 'CROP_OFFLINE_STATUS' });
  })().catch((error) => {
    console.warn(
      'Offline preparation could not finish:',
      error instanceof Error ? error.message : 'unknown error',
    );
  });
  return started;
}

export function useOfflineReady(): boolean {
  const [value, setValue] = useState(ready);
  useEffect(() => {
    const update = () => setValue(true);
    window.addEventListener('crop-offline-ready', update);
    void registerOfflineSupport();
    return () => window.removeEventListener('crop-offline-ready', update);
  }, []);
  return value;
}
