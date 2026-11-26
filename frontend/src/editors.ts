/** Lazy chunk: everything needed to edit rules (loaded on first use). */
import { LaeutwerkColorPopup } from "./color-picker";
import { LaeutwerkField } from "./ha-field";
import { LaeutwerkNewRule } from "./new-rule";
import { LaeutwerkHelpTip } from "./help-tip";
import { LaeutwerkKeywordLook } from "./keyword-look";
import { defineElements } from "./register";
import { LaeutwerkRuleEditor } from "./rule-editor";
import { LaeutwerkRuleHistory } from "./rule-history";
import { LaeutwerkSignalEditor } from "./signal-editor";
import { LaeutwerkSuggest } from "./suggest-field";
import { LaeutwerkTemplatePicker } from "./template-picker";

export const ready = defineElements([
  ["laeutwerk-rule-editor", LaeutwerkRuleEditor],
  ["laeutwerk-rule-history", LaeutwerkRuleHistory],
  ["laeutwerk-signal-editor", LaeutwerkSignalEditor],
  ["laeutwerk-field", LaeutwerkField],
  ["laeutwerk-help-tip", LaeutwerkHelpTip],
  ["laeutwerk-keyword-look", LaeutwerkKeywordLook],
  ["laeutwerk-suggest", LaeutwerkSuggest],
  ["laeutwerk-new-rule", LaeutwerkNewRule],
  ["laeutwerk-template-picker", LaeutwerkTemplatePicker],
  ["laeutwerk-color-popup", LaeutwerkColorPopup],
]);
