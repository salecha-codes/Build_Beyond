import { useEffect, useRef, useState } from 'react';
import { Pause, Play, Volume2 } from 'lucide-react';
import { translateUi } from '../lib/content';
import type { Language } from '../lib/types';

export function AudioPlayer({
  src,
  label,
  compact = false,
  language = 'en',
}: {
  src?: string | null;
  label: string;
  compact?: boolean;
  language?: Language;
}) {
  const t = (en: string) => translateUi(en, en, language);
  const audio = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [failed, setFailed] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [duration, setDuration] = useState(0);
  useEffect(() => {
    setPlaying(false);
    setFailed(false);
    setElapsed(0);
    setDuration(0);
    return () => audio.current?.pause();
  }, [src]);
  async function toggle() {
    const element = audio.current;
    if (!element) return;
    try {
      if (element.paused) {
        if (element.ended) element.currentTime = 0;
        await element.play();
      } else element.pause();
    } catch {
      setFailed(true);
    }
  }
  return (
    <div className={compact ? 'audio-player compact' : 'audio-player'}>
      {src && (
        <audio
          ref={audio}
          src={src}
          preload="metadata"
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
          onError={() => setFailed(true)}
          onLoadedMetadata={() => setDuration(audio.current?.duration || 0)}
          onTimeUpdate={() => setElapsed(audio.current?.currentTime || 0)}
        />
      )}
      <button
        data-testid="audio-toggle"
        className="audio-play"
        onClick={toggle}
        disabled={!src || failed}
        aria-label={`${playing ? t('Pause') : t('Play')} ${label}`}
      >
        {playing ? (
          <Pause size={19} />
        ) : compact ? (
          <Volume2 size={19} />
        ) : (
          <Play size={19} fill="currentColor" />
        )}
      </button>
      <div className="audio-copy">
        <strong>{failed ? t('Audio unavailable') : label}</strong>
        {!compact && (
          <>
            <div className="waveform" aria-hidden="true">
              {[7, 13, 21, 12, 27, 19, 10, 22, 30, 15, 24, 11, 18, 26, 14, 21, 9, 16, 23, 12].map(
                (h, i) => (
                  <i
                    key={i}
                    style={{
                      height: h,
                      opacity: duration && i / 20 <= elapsed / duration ? 1 : 0.34,
                    }}
                  />
                ),
              )}
            </div>
            <span>
              {duration > 0
                ? `${Math.floor(elapsed / 60)}:${Math.floor(elapsed % 60)
                    .toString()
                    .padStart(2, '0')} / ${Math.floor(duration / 60)}:${Math.floor(duration % 60)
                    .toString()
                    .padStart(2, '0')}`
                : t('Bundled offline audio')}
            </span>
          </>
        )}
      </div>
    </div>
  );
}
