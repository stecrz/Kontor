// Checks of the interface code in CI (only rules that point at real mistakes): run from the repository's top folder with
//   npx eslint -c .github/eslint.config.mjs web
import globals from "globals";

const mistakes = {
  "no-undef": "error", "no-redeclare": "error", "no-dupe-keys": "error", "no-duplicate-case": "error",
  "no-dupe-else-if": "error", "no-unreachable": "error", "no-self-assign": "error", "no-const-assign": "error",
  "no-dupe-args": "error", "no-func-assign": "error", "no-import-assign": "error", "use-isnan": "error",
  "valid-typeof": "error", "no-unsafe-negation": "error", "no-sparse-arrays": "error", "no-cond-assign": ["error", "except-parens"],
};

export default [
  { files: ["web/app.js"], languageOptions: { ecmaVersion: "latest", sourceType: "script",
      globals: { ...globals.browser, I18N: "readonly" } }, rules: mistakes },
  { files: ["web/i18n.js"], languageOptions: { ecmaVersion: "latest", sourceType: "script", globals: globals.browser }, rules: mistakes },
  { files: ["web/sw.js"], languageOptions: { ecmaVersion: "latest", sourceType: "script", globals: globals.serviceworker }, rules: mistakes },
];
