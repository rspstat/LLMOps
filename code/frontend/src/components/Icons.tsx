import type { ReactNode, SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

/** 24x24 line icons, drawn here so the page needs no icon library. */
function Icon({ children, ...props }: IconProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="1em"
      height="1em"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {children}
    </svg>
  );
}

export const SunIcon = (props: IconProps) => (
  <Icon {...props}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </Icon>
);

export const MoonIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
  </Icon>
);

export const ShieldIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z" />
    <path d="M9 12l2 2 4-4" />
  </Icon>
);

export const RouteIcon = (props: IconProps) => (
  <Icon {...props}>
    <circle cx="6" cy="6" r="2.2" />
    <circle cx="18" cy="6" r="2.2" />
    <circle cx="12" cy="19" r="2.2" />
    <path d="M6 8.2v1.3c0 1.7 1.3 3 3 3h6c1.7 0 3-1.3 3-3V8.2M12 12.5v4.3" />
  </Icon>
);

export const ChipIcon = (props: IconProps) => (
  <Icon {...props}>
    <rect x="6" y="6" width="12" height="12" rx="2" />
    <rect x="9.5" y="9.5" width="5" height="5" rx="1" />
    <path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3" />
  </Icon>
);

export const ReplyIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.5-4.6A8 8 0 1 1 21 12z" />
    <path d="M8.5 12h.01M12 12h.01M15.5 12h.01" />
  </Icon>
);

export const SendIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d="M4 12l16-8-6 16-2.5-6.5z" />
  </Icon>
);

export const CheckIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d="M5 12.5l4.5 4.5L19 7.5" />
  </Icon>
);

export const CrossIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Icon>
);

export const AlertIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d="M12 3.5l9 15.5H3z" />
    <path d="M12 10v4M12 17h.01" />
  </Icon>
);

export const LogoMark = (props: IconProps) => (
  <svg viewBox="0 0 32 32" width="1em" height="1em" aria-hidden="true" focusable="false" {...props}>
    <defs>
      <linearGradient id="logo-gradient" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" style={{ stopColor: "var(--accent)" }} />
        <stop offset="1" style={{ stopColor: "var(--accent-2)" }} />
      </linearGradient>
    </defs>
    <rect width="32" height="32" rx="9" fill="url(#logo-gradient)" />
    <path
      d="M8 22V10M8 16h6a4 4 0 0 0 4-4v-2M14 16h4a4 4 0 0 1 4 4v2"
      fill="none"
      stroke="#fff"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <circle cx="18" cy="9" r="2" fill="#fff" />
    <circle cx="22" cy="23" r="2" fill="#fff" />
  </svg>
);
