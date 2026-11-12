/** Lazy chunk: the visual card editor. */
import { LaeutwerkCardEditor } from "./card-editor";
import { LaeutwerkField } from "./ha-field";
import { LaeutwerkHelpTip } from "./help-tip";
import { defineElements } from "./register";

export const ready = defineElements([
  ["laeutwerk-card-editor", LaeutwerkCardEditor],
  ["laeutwerk-field", LaeutwerkField],
  ["laeutwerk-help-tip", LaeutwerkHelpTip],
]);
