import { forwardRef, useId, type SVGProps } from "react";

type GroupProps = SVGProps<SVGGElement>;

export interface BeelineLogoProps extends SVGProps<SVGSVGElement> {
  size?: number | string;
  yellow?: string;
  black?: string;
  flat?: boolean;
  title?: string;
  parts?: {
    sphere?: GroupProps;
    stripes?: GroupProps;
    upperStripe?: GroupProps;
    lowerStripe?: GroupProps;
    lighting?: GroupProps;
  };
}

/** Vector recreation supplied for RouteFlow; no bitmap or external asset. */
export const BeelineLogo = forwardRef<SVGSVGElement, BeelineLogoProps>(
  function BeelineLogo(
    { size = 160, yellow = "#ffc800", black = "#050505", flat = false, title = "Билайн", parts = {}, ...svgProps },
    ref,
  ) {
    const uid = useId().replace(/:/g, "");
    const clip = `beeline-clip-${uid}`;
    const light = `beeline-light-${uid}`;
    const rim = `beeline-rim-${uid}`;
    const titleId = `beeline-title-${uid}`;

    return <svg
      ref={ref}
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 448 448"
      fill="none"
      role={title ? "img" : undefined}
      aria-labelledby={title ? titleId : undefined}
      aria-hidden={title ? undefined : true}
      {...svgProps}
    >
      {title && <title id={titleId}>{title}</title>}
      <defs>
        <clipPath id={clip}><circle cx="224" cy="224" r="189" /></clipPath>
        <linearGradient id={light} x1="154" y1="36" x2="250" y2="271" gradientUnits="userSpaceOnUse">
          <stop stopColor="white" stopOpacity="0.34" />
          <stop offset="0.44" stopColor="white" stopOpacity="0.09" />
          <stop offset="0.8" stopColor="white" stopOpacity="0" />
        </linearGradient>
        <radialGradient id={rim} cx="0" cy="0" r="1" gradientTransform="translate(218 223) rotate(90) scale(210 207)" gradientUnits="userSpaceOnUse">
          <stop offset="0.48" stopColor="white" stopOpacity="0" />
          <stop offset="0.83" stopColor="white" stopOpacity="0.08" />
          <stop offset="1" stopColor="white" stopOpacity="0.3" />
        </radialGradient>
      </defs>
      <g data-part="sphere" {...parts.sphere}>
        <g clipPath={`url(#${clip})`}>
          <circle data-part="base" cx="224" cy="224" r="189" fill={black} />
          <g data-part="stripes" fill={yellow} {...parts.stripes}>
            <g data-part="upper-stripe" {...parts.upperStripe}>
              <path d="M216 35C251 34 260 56 241 86C220 120 173 151 126 165C88 176 61 172 58 158C56 149 59 140 65 128C46 159 35 191 35 224C36 251 61 267 100 265C161 264 239 224 289 172C329 131 346 85 323 64C294 46 256 35 216 35Z" />
            </g>
            <g data-part="lower-stripe" {...parts.lowerStripe}>
              <path d="M384 123C403 171 383 216 345 257C298 307 224 341 161 348C112 353 78 341 61 318C76 346 95 370 124 388C142 400 161 403 187 399C247 391 313 360 358 318C391 287 409 257 412 238C416 198 405 155 384 123Z" />
            </g>
          </g>
          {!flat && <g data-part="lighting" pointerEvents="none" {...parts.lighting}>
            <circle cx="224" cy="224" r="189" fill={`url(#${light})`} />
            <circle cx="224" cy="224" r="189" fill={`url(#${rim})`} />
          </g>}
        </g>
      </g>
    </svg>;
  },
);

export default BeelineLogo;
