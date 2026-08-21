/** The file-format marks used on download controls.
 *
 *  Inline SVG rather than a sprite or an icon-font lookup: these sit on every
 *  report row, so they must paint with the row and without a second request.
 *  Both take `currentColor`, unlike the provider brand marks on the login page
 *  — these are our own glyphs, so they inherit the button's colour and work
 *  unchanged in dark mode.
 */

export function PdfIcon({ className }: { className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" aria-hidden className={className}>
      <path d="M0 0h24v24H0z" fill="none" />
      <path
        fill="currentColor"
        fillRule="evenodd"
        d="M12.5 3.505h-7V12H4V2h9.56L20 8.44V12h-1.5V9.5h-4.75c-.69 0-1.25-.56-1.25-1.25zM17.44 8L14 4.56V8zM4 13.5h3.75c.69 0 1.25.56 1.25 1.25v3C9 18.44 8.44 19 7.75 19H5.5v3H4zm1.5 4h2V15h-2zm8.25-4H10V22h3.75c.69 0 1.25-.56 1.25-1.25v-6c0-.69-.56-1.25-1.25-1.25m6.75 0V15h-3v2.5H20V19h-2.5v3H16v-8.5zm-7 7h-2V15h2z"
        clipRule="evenodd"
      />
    </svg>
  );
}

export function PptxIcon({ className }: { className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" aria-hidden className={className}>
      <path d="M0 0h16v16H0z" fill="none" />
      <path
        fill="currentColor"
        fillRule="evenodd"
        d="M14 4.5V11h-1V4.5h-2A1.5 1.5 0 0 1 9.5 3V1H4a1 1 0 0 0-1 1v9H2V2a2 2 0 0 1 2-2h5.5zM1.5 11.85h1.6q.434 0 .732.179q.302.175.46.477t.158.677t-.16.677q-.159.299-.464.474a1.45 1.45 0 0 1-.732.173H2.29v1.342H1.5zm2.06 1.714a.8.8 0 0 0 .085-.381q0-.34-.185-.521q-.185-.182-.513-.182h-.659v1.406h.66a.8.8 0 0 0 .374-.082a.57.57 0 0 0 .238-.24m1.302-1.714h1.6q.434 0 .732.179q.302.175.46.477t.158.677t-.16.677q-.158.299-.464.474a1.45 1.45 0 0 1-.732.173h-.803v1.342h-.79zm2.06 1.714a.8.8 0 0 0 .085-.381q0-.34-.185-.521q-.184-.182-.513-.182H5.65v1.406h.66a.8.8 0 0 0 .374-.082a.57.57 0 0 0 .238-.24m2.852 2.285v-3.337h1.137v-.662H7.846v.662H8.98v3.337zm3.796-3.999h.893l-1.274 2.007l1.254 1.992h-.908l-.85-1.415h-.035l-.853 1.415h-.861l1.24-2.016l-1.228-1.983h.931l.832 1.439h.035z"
      />
    </svg>
  );
}
