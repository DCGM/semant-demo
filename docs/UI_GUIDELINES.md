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
- Use a toggle switch for a setting that is on or off (such as **Allow multiple values** or
  **Show retired**); use checkboxes to choose items of a set (rows, values, filter options).

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
- Check layouts and interaction states at the relevant desktop and phone widths, following
  the [UI change checklist](../CONTRIBUTING.md#ui-change-checklist).

Document deliberate exceptions in the relevant PR. Add new guidelines only when an
interaction decision is broadly reusable; feature-specific behavior belongs with that
feature's requirements or documentation.
