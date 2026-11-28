/** Variables supplied by other integrations (e.g. Randowerk), cached per session. */
import { filterSuggestions, templateVariables } from "./format";
import type { HomeAssistant } from "./types";

export interface ProviderVariable {
  name: string;
  description?: string;
  example?: string;
}

export interface ProviderInfo {
  key: string;
  title: string;
  variables: ProviderVariable[];
}

export interface VariableSuggestion {
  value: string;
  /** Group heading (provider title); undefined = built-in variable. */
  group?: string;
  description?: string;
}

let cache: ProviderInfo[] = [];
let lang = "en";
let pending: Promise<void> | undefined;

export function getProviders(): ProviderInfo[] {
  return cache;
}

/** Load the catalog (once; `force` refetches). Older backends: empty list. */
export function loadProviders(
  hass: Pick<HomeAssistant, "callWS" | "language"> | undefined,
  force = false,
): Promise<void> {
  if (!hass) return Promise.resolve();
  if (pending && !force) return pending;
  lang = hass.language ?? "en";
  pending = hass
    .callWS<{ providers?: ProviderInfo[] }>({ type: "laeutwerk/variables/providers" })
    .then((res) => {
      cache = res?.providers ?? [];
    })
    .catch(() => {
      cache = [];
    });
  return pending;
}

/** Test helper. */
export function setProviders(providers: ProviderInfo[], language = "en"): void {
  cache = providers;
  lang = language;
  pending = Promise.resolve();
}

export function providerNames(providers: ProviderInfo[] = cache): string[] {
  return providers.flatMap((p) => p.variables.map((v) => v.name));
}

/** name → example, to fill local previews. */
export function providerExamples(providers: ProviderInfo[] = cache): Record<string, string> {
  const out: Record<string, string> = {};
  for (const p of providers)
    for (const v of p.variables) if (v.example !== undefined) out[v.name] = v.example;
  return out;
}

/** Built-in variables first, then each provider as a group; filtered by the typed query. */
export function variableSuggestions(
  names: string[],
  query: string,
  providers: ProviderInfo[] = cache,
  language = lang,
): VariableSuggestion[] {
  const out: VariableSuggestion[] = filterSuggestions(
    names.map((value) => ({ value })),
    query,
  );
  const eg = language.startsWith("de") ? "z. B." : "e.g.";
  for (const p of providers) {
    const items = filterSuggestions(
      p.variables.map((v) => ({
        value: v.name,
        group: p.title,
        description: [v.description, v.example ? `${eg} ${v.example}` : ""]
          .filter(Boolean)
          .join(" · "),
      })),
      query,
    );
    out.push(...items);
  }
  return out;
}

/** Placeholders in `texts` that are neither known nor provided. */
export function unknownVariables(
  texts: (string | null | undefined)[],
  known: Iterable<string>,
  providers: ProviderInfo[] = cache,
): string[] {
  const ok = new Set([...known, ...providerNames(providers)]);
  const bad = new Set<string>();
  for (const t of texts) for (const n of templateVariables(t ?? "")) if (!ok.has(n)) bad.add(n);
  return [...bad];
}
