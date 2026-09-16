/**
 * The first thing a keyboard reaches on any page: a way past the header's
 * links straight to the page's own content. It is invisible until it takes
 * focus, and then it sits over the top-left corner where it can be read.
 */
export function SkipLink() {
  return (
    <a
      href="#main"
      data-touch-target
      className="absolute start-4 top-4 z-50 inline-flex -translate-y-24 items-center rounded-lg border border-teal bg-paper-raised px-4 py-3 text-[14px] font-medium text-teal transition-transform focus:translate-y-0 focus-visible:translate-y-0"
      data-testid="skip-to-content"
    >
      Skip to the main content
    </a>
  );
}
