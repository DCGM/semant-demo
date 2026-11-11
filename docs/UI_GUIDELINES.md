# UI guidelines

These are baseline interaction rules for new or changed semANT interfaces. Prefer existing
shared components and terminology over new patterns. This is not a visual style guide or
a requirement to redesign existing screens; extend it when recurring problems or agreed
product decisions justify another rule.

## Clarity and feedback

- Use clear, consistent names for actions and states. Distinguish similar actions (such
  as **Retire** versus **Delete**) and explain consequences users cannot readily infer.
- Show meaningful loading, empty, success and failure states. Empty states should suggest
  an action the user can actually perform.
- Do not report success until the operation is confirmed. On failure, explain what
  happened and offer a retry or next step where possible. For batch actions, distinguish
  completed items from failures or uncertain outcomes.

## Forms and dialogs

- Validate near the affected field, with specific messages. Preserve entered values when
  validation or a save fails.
- Show an error at the field it concerns. When a dialog's body scrolls, a message about the
  whole form must be scrolled into view; a message at the end of a long form is easily missed.
- During an asynchronous save, show progress and prevent duplicate submissions. Disable
  fields and controls that could change the submitted values until the request completes;
  also prevent accidental dismissal when the save cannot safely be cancelled.
- For dialogs that perform their own save, close only after confirmed success and update
  the UI from the authoritative result. Existing dialogs that close before handing off a
  save should not be copied as a default pattern.
- Warn before discarding meaningful unsaved changes; do not block closing an unchanged form.
- By default, use a toggle switch for an independent setting that is on or off (such as
  **Allow multiple values** or **Show retired**), and checkboxes to choose items of a set (rows,
  values, filter options). This is a convention, not an absolute rule: a well-justified exception
  is fine when the PR or the code documents it.

## Consequential changes

- Explain destructive or hard-to-reverse actions before confirmation, including known
  effects on related data. Do not silently remove, reclassify or overwrite user work.
- Make available recovery paths clear, such as **Undo** or **Retire instead**, where
  supported. Avoid offering recovery that the backend cannot provide.

## Navigation and accessibility

- Preserve useful context (selection, filters, position) when moving between related views
  where practical; support direct links to meaningful views.
- Make controls usable by keyboard and touch. Give icon-only actions accessible labels;
  do not rely on hover tooltips for essential meaning.
- When a table has more columns than a narrow screen fits, give its key columns minimum widths
  and let the table scroll sideways in its own container, never the page; keep what identifies
  a row (its checkbox and key column) in view while scrolling (the annotation concordance, #537).
- Check layouts and interaction states at the relevant desktop and phone widths, following
  the [UI change checklist](#ui-change-checklist).

Document deliberate exceptions in the relevant PR. Add new guidelines only when an
interaction decision is broadly reusable; feature-specific behavior belongs with that
feature's requirements or documentation.

## UI change checklist

Applies to meaningful UI changes: layout, components, responsive behavior, interaction or
visible states. Match inspection to likely impact, not a fixed quota. Backend/nonvisual
work, documentation and trivial cosmetic edits need no checklist; a small localized
styling change needs only a spot-check. Explain omitted evidence when reviewers might
expect it. Browser-test requirements remain in
[CONTRIBUTING](../CONTRIBUTING.md#4-testing-contract).

1. **Inspect before the first push/review.** For new views, shared layouts or responsive
   changes, check wide desktop, constrained desktop (both sidebars open where present)
   and phone. For local interaction/styling changes, inspect only affected states and
   widths. `make e2e-dev-capture` provides 1920x1000, 1280x900 and 390x844 fixtures; pass
   a spec to capture the changed state ([capture guide](DEVELOPMENT.md#fast-browser-test-loop)).
2. **Attach proportionate evidence.** Use before/after or final screenshots, or a short
   recording, of changed states (selected, expanded, empty, signed out, etc.), not just
   the default view. Name relevant states/contexts not captured. Only synthetic/fixture
   data, and only captures you actually made; unaffected widths need no screenshots.
3. **Review what applies.** Check card/title/metadata alignment, wrapping/overflow, long
   titles and narrow toolbars, selected/hover/focus states, authorization/ownership-gated
   controls, keyboard/touch interaction and direct links/reloads. This is a review aid,
   not a requirement to add browser tests for every visual check.
4. **Report verification honestly.** State actual commands/results and any outstanding
   full `make test-e2e` run; targeted specs do not replace required final validation.

### Screenshot uploads

Check `gh --version` and `gh auth status` first. The upload commands require GitHub CLI
2.99 or newer; agents should ask for an update rather than improvise an upload mechanism.
If uploading fails, report the blocker and ask the user to upload in the browser. Do not
set up external hosting such as gists.

```bash
gh pr edit <N> --attach './shot.png#What the screenshot shows'
gh pr comment <N> --attach './shot.png#What the screenshot shows'
```

The first appends to the description; the second adds a comment. Repeat `--attach` for
multiple files and give each descriptive alt text after `#`. To place images in a body
file (for example, in a table), write `![alt](./shot.png)` and pass
`-F body.md --attach ./shot.png`; paths are rewritten to uploaded assets. Verify rendering:
`gh pr view <N> --json body` should contain `github.com/user-attachments/...` URLs.

New UI issues use the [UI change template](../.github/ISSUE_TEMPLATE/ui-change.md): requested
behavior, appearance, target widths, an existing reference image if available, and
non-goals. Words or a rough sketch suffice; pixel-perfect mockups are not required, and
nonvisual bugs need none of this.
