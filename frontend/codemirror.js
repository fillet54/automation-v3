// The CodeMirror the workspace editor uses (static/js/editor.js), as one
// global: CM.editor(parent, {text, language, onChange, keys}) makes an
// editor; the rest is exported for the language client, and `snippet`
// for inserting snippets (framework/snippets.py) with fields to step through.
//
// Rebuild after changing this file: npm install && npm run build
import { EditorState, Compartment } from "@codemirror/state";
import {
  EditorView, keymap, drawSelection, highlightSpecialChars, placeholder, tooltips, hoverTooltip,
} from "@codemirror/view";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import {
  StreamLanguage, bracketMatching, indentOnInput, syntaxHighlighting, HighlightStyle,
} from "@codemirror/language";
import {
  closeBrackets, closeBracketsKeymap, autocompletion, completionKeymap, snippet,
} from "@codemirror/autocomplete";
import { linter, setDiagnostics, lintKeymap } from "@codemirror/lint";
import { searchKeymap, highlightSelectionMatches } from "@codemirror/search";
import { clojure } from "@codemirror/legacy-modes/mode/clojure";
import { tags } from "@lezer/highlight";

// Colours come from the page's stylesheet (paper-ui's variables)
const theme = EditorView.theme({
  "&": { color: "var(--ui-ink)", backgroundColor: "transparent", fontSize: "var(--ui-text-sm)" },
  "&.cm-focused": { outline: "none" },
  ".cm-content": { fontFamily: "var(--ui-font-mono)", padding: "8px 0", caretColor: "var(--ui-ink)" },
  ".cm-line": { padding: "0 10px" },
  ".cm-cursor": { borderLeftColor: "var(--ui-ink)" },
  ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": {
    backgroundColor: "color-mix(in srgb, var(--ui-accent) 22%, transparent)",
  },
  ".cm-tooltip": {
    backgroundColor: "var(--ui-paper)", color: "var(--ui-ink)", border: "1px solid var(--ui-rule)",
    borderRadius: "var(--ui-radius)", fontSize: "var(--ui-text-sm)",
  },
  ".cm-tooltip-autocomplete ul li[aria-selected]": {
    backgroundColor: "color-mix(in srgb, var(--ui-accent) 18%, var(--ui-paper))", color: "var(--ui-ink)",
  },
  ".cm-matchingBracket": { backgroundColor: "color-mix(in srgb, var(--ui-accent) 25%, transparent)", outline: "none" },
});

const highlight = HighlightStyle.define([
  { tag: tags.comment, color: "var(--ui-muted)", fontStyle: "italic" },
  { tag: [tags.string, tags.special(tags.string)], color: "var(--ui-success)" },
  { tag: [tags.number, tags.bool, tags.null, tags.atom], color: "var(--ui-warning)" },
  { tag: [tags.keyword, tags.definitionKeyword], color: "var(--ui-accent)", fontWeight: "500" },
  { tag: tags.bracket, color: "var(--ui-muted)" },
]);

const languages = { rvt: () => StreamLanguage.define(clojure) };

// An editor in `parent`. options: text; language ("rvt" for script code,
// else plain text); onChange(text); onMove(view), called when the text
// or the cursor changes; keys ([{key, run}], tried first); placeholder;
// extensions (more CodeMirror extensions)
function editor(parent, options) {
  options = options || {};
  const extensions = [
    highlightSpecialChars(), history(), drawSelection(), indentOnInput(),
    syntaxHighlighting(highlight), highlightSelectionMatches(),
    keymap.of([...(options.keys || []), ...closeBracketsKeymap, ...defaultKeymap, ...historyKeymap,
               ...searchKeymap, ...completionKeymap, ...lintKeymap, indentWithTab]),
    EditorView.lineWrapping, theme, tooltips({ parent: document.body }),
    EditorView.updateListener.of((update) => {
      if (update.docChanged && options.onChange) options.onChange(update.state.doc.toString());
      if ((update.docChanged || update.selectionSet) && options.onMove) options.onMove(update.view);
    }),
  ];
  if (options.language && languages[options.language]) {
    extensions.push(languages[options.language](), bracketMatching(), closeBrackets());
  }
  if (options.placeholder) extensions.push(placeholder(options.placeholder));
  if (options.extensions) extensions.push(...options.extensions);
  const view = new EditorView({
    parent, state: EditorState.create({ doc: options.text || "", extensions }),
  });
  return view;
}

export {
  editor, EditorState, EditorView, Compartment, keymap, autocompletion, linter, setDiagnostics,
  hoverTooltip, snippet,
};
