"""Import page scans, page layout files and chunk-start anchors for the existing corpus (#542).

Two separate, explicitly run steps (``docs/DATA_MAINTENANCE.md``):

1. ``assets`` writes the page asset store (#541) from the original PERO PAGE XML and scans
   named by a ``page_order`` export (#571): page layout files, scans, thumbnails, the manifest
   and an anchor plan per document. It reads the stored chunks read-only and writes nothing to
   any database.
2. ``anchors`` stores the planned ``layoutStart`` on the existing chunks (``--write``, with
   ``--confirm-endpoint``) or reports what it would change (``--check``, the default).

No chunk text, id, order, position, vector, page field or annotation is changed; the page
fields (``start_page_id``, ``from_page``, ``to_page``) are compared with the anchors and
reported only. Both steps can be interrupted and run again.
"""
