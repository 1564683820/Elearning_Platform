import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

const paths = {
  scan: 'M4 7V5a1 1 0 0 1 1-1h2m10 0h2a1 1 0 0 1 1 1v2m0 10v2a1 1 0 0 1-1 1h-2M7 20H5a1 1 0 0 1-1-1v-2m0-5h16',
  user: 'M20 21a8 8 0 0 0-16 0m12-13a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z',
  lock: 'M7 11V8a5 5 0 0 1 10 0v3M5 11h14v10H5zM12 15v2',
  eye: 'M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Zm10 2a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z',
  home: 'm3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Zm6 11v-7h6v7',
  files: 'M15 21H5a1 1 0 0 1-1-1V8m4 9V3h8l4 4v10Zm8-14v5h4',
  clipboard: 'M9 5H6a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1h-3M9 3h6v4H9zm3 9h4m-4 4h4m-8-4h.01m-.01 4h.01',
  sidebar: 'M3 5h18v14H3zM15 5v14m-7-4 3-3-3-3',
  plus: 'M12 5v14M5 12h14',
  edit: 'M11 4H5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-6M9 15l1-4 8.5-8.5a2.1 2.1 0 0 1 3 3L13 14z',
  close: 'm6 6 12 12M18 6 6 18',
  warning: 'M12 3 2.8 19h18.4L12 3zm0 6v4m0 3v.1',
  info: 'M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0ZM12 11v6m0-10v.1',
  archive: 'M4 4h16v4H4zm1 4v12h14V8m-9 4h4',
  refresh: 'M3 12a9 9 0 1 1 2.7 6.4M3 6v6h6',
  upload: 'M12 16V3m-5 5 5-5 5 5M4 14v6h16v-6',
  skill: 'M5 3h9l5 5v13H5zm9 0v5h5m-9 5-2 2 2 2m4-4 2 2-2 2',
  template: 'M3 4h5v5H3zm0 11h5v5H3zm9-10h9m-9 4h9m-9 7h9m-9 4h9',
  more: 'M5 12h.01M12 12h.01M19 12h.01',
  up: 'M12 19V5m-6 6 6-6 6 6',
  upRight: 'M7 17 17 7M7 7h10v10',
  right: 'm9 18 6-6-6-6',
  left: 'm15 18-6-6 6-6',
  down: 'm6 9 6 6 6-6',
  hash: 'M4 9h16M3 15h16M10 3 6 21m12-18-4 18',
  check: 'm5 12 4 4L19 6',
  search: 'M21 21l-4.3-4.3M18 11a7 7 0 1 1-14 0 7 7 0 0 1 14 0Z',
  searchOff: 'm21 21-4.3-4.3M18 11a7 7 0 1 1-14 0 7 7 0 0 1 14 0Zm-9-2 4 4m0-4-4 4',
  chart: 'M5 20v-7m7 7V4m7 16V9',
  bubble: 'M20 11a8 8 0 0 1-8 8 9 9 0 0 1-3.5-.7L4 20l1.5-4.5A8 8 0 1 1 20 11Z',
  messages: 'M3 13a2 2 0 0 0 2-2V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H7l-4 3v-3Zm7 3v2a2 2 0 0 0 2 2h5l4 2V10a2 2 0 0 0-2-2',
  shield: 'M12 22s7-3 7-9V5l-7-3-7 3v8c0 6 7 9 7 9Zm-3-10 2 2 4-4',
  mail: 'M3 5h18v14H3zm0 2 9 6 9-6',
  settings: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM12 2v3m0 14v3M2 12h3m14 0h3M5 5l2 2m10 10 2 2M5 19l2-2M17 7l2-2',
  sparkle: 'M9 3l2 6 6 2-6 2-2 6-2-6-6-2 6-2Zm9 10 1 3 3 1-3 1-1 3-1-3-3-1 3-1Z',
  image: 'M3 4h18v16H3zm0 12 5-5 4 4 3-3 6 6m-5-9h.01',
  camera: 'M3 7h4l2-3h6l2 3h4v13H3zM16 13a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z',
  cameraOff: 'm3 3 18 18M7 7H3v13h14M10 4h5l2 3h4v10M9 11a4 4 0 0 0 5 5',
  logout: 'M10 17l5-5-5-5m5 5H3m9-8h7a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-7',
};

export function Icon({ name, size = 20 }: { name: keyof typeof paths; size?: number }) {
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round"><path d={paths[name]} /></svg>;
}

export function Select({ label, value, options, onChange }: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const root = useRef<HTMLDivElement>(null);
  const selected = Math.max(0, options.findIndex(item => item.value === value));

  useEffect(() => {
    if (!open) return;
    function dismiss(event: PointerEvent) {
      if (event.target instanceof Node && !root.current?.contains(event.target)) setOpen(false);
    }
    document.addEventListener('pointerdown', dismiss);
    return () => document.removeEventListener('pointerdown', dismiss);
  }, [open]);

  function pick(index: number) {
    if (options[index]) onChange(options[index].value);
    setOpen(false);
  }

  function keyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === 'Escape' || event.key === 'Tab') {
      if (open && event.key === 'Escape') event.preventDefault();
      setOpen(false);
    } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const direction = event.key === 'ArrowDown' ? 1 : -1;
      setActive(open ? Math.max(0, Math.min(options.length - 1, active + direction)) : selected);
      setOpen(true);
    } else if (open && (event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault();
      pick(active);
    }
  }

  return <div className="select" ref={root}>
    <button type="button" role="combobox" aria-label={label} aria-expanded={open} aria-controls={open ? listId : undefined}
      aria-activedescendant={open ? `${listId}-${active}` : undefined} onKeyDown={keyDown}
      onClick={() => { setActive(selected); setOpen(!open); }}>
      <span>{options[selected]?.label}</span><Icon name="down" size={18} />
    </button>
    {open && <ul role="listbox" aria-label={label} id={listId}>
      {options.map((item, index) => <li key={item.value} role="option" aria-selected={item.value === value}
        data-highlighted={index === active} id={`${listId}-${index}`} onPointerMove={() => setActive(index)}
        onPointerDown={event => event.preventDefault()} onClick={() => pick(index)}>
        <span>{item.label}</span>{item.value === value && <Icon name="check" size={17} />}
      </li>)}
    </ul>}
  </div>;
}

export function Sheet({ title, close, children, variant, icon, portalClassName }: {
  title: string; close: () => void; children: ReactNode;
  variant?: 'attachments' | 'logout' | 'draft' | 'archive' | 'skill' | 'paper-review' | 'paper-finish' | 'paper-conflict' | 'camera-permission';
  icon?: keyof typeof paths;
  portalClassName?: string;
}) {
  const dialog = useRef<HTMLElement>(null);
  useEffect(() => {
    const trigger = document.activeElement;
    dialog.current?.focus();
    return () => { if (trigger instanceof HTMLElement && trigger.isConnected) trigger.focus(); };
  }, []);
  const overlay = <div className="overlay">
    <button className="backdrop" onClick={close} aria-label="关闭弹窗" />
    <section ref={dialog} tabIndex={-1} className={`sheet ${variant ? `sheet-${variant}` : ''}`}
      role="dialog" aria-modal="true" aria-label={title} onKeyDown={event => {
        if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(); }
      }}>
      <span className="handle" />
      <h2>{icon && <span><Icon name={icon} /></span>}{variant === 'logout' && <span><Icon name="logout" /></span>}{variant === 'draft' && <span><Icon name="files" /></span>}{variant === 'archive' && <span><Icon name="archive" /></span>}{variant === 'skill' && <span><Icon name="upload" /></span>}{title}</h2>{children}
    </section>
  </div>;
  return portalClassName ? createPortal(<div className={portalClassName}>{overlay}</div>, document.body) : overlay;
}

export function errorText(error: unknown) {
  return error instanceof Error ? error.message : '操作失败，请重试';
}
