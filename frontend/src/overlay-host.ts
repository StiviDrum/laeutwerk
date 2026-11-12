/** Overlays must live inside <home-assistant> so HA's Lit context reaches their pickers. */
export function overlayHost(): ParentNode {
  return document.querySelector("home-assistant")?.shadowRoot ?? document.body;
}
