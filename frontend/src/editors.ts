/** Lazy chunk: everything needed to edit rules (loaded on first use). */
import { LaeutwerkColorPopup } from "./color-picker";
import { LaeutwerkField } from "./ha-field";
import { LaeutwerkHelpTip } from "./help-tip";
import { LaeutwerkKeywordLook } from "./keyword-look";
import { defineElements } from "./register";
import { LaeutwerkRuleEditor } from "./rule-editor";
import { LaeutwerkSignalEditor } from "./signal-editor";
import { LaeutwerkSuggest } from "./suggest-field";
import { LaeutwerkTaskDialog } from "./task-dialog";
import { LaeutwerkTemplatePicker } from "./template-picker";

export const ready = defineElements([
  ["laeutwerk-rule-editor", LaeutwerkRuleEditor],
  ["laeutwerk-signal-editor", LaeutwerkSignalEditor],
  ["laeutwerk-field", LaeutwerkField],
  ["laeutwerk-help-tip", LaeutwerkHelpTip],
  ["laeutwerk-keyword-look", LaeutwerkKeywordLook],
  ["laeutwerk-suggest", LaeutwerkSuggest],
  ["laeutwerk-template-picker", LaeutwerkTemplatePicker],
  ["laeutwerk-task-dialog", LaeutwerkTaskDialog],
  ["laeutwerk-color-popup", LaeutwerkColorPopup],
]);
