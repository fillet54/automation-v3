====================
Boot Image Selection
====================
Boots with the primary image valid and corrupted, and through a run of
quick resets, and checks which image boots. The primary image's state is
a software load, so each is a variation of its own.

Requirements
------------
1. :req:`VM-EXE-006`

.. rvt::

   (variations "primary-ok"
     ["primary valid"     [true]
      "primary corrupted" [false]])

Steps
-----

.. rvt:: Load the images

   (TBD "Load a valid primary and backup image; if primary-ok is false, corrupt one byte of the primary image")

.. rvt:: Each run of resets
   :table:

   ("quick-resets"
     ["one reset"    [1]
      "two resets"   [2]
      "three resets" [3]])

   (TBD "Cause quick-resets watchdog resets, each within quick-reset-window-s (60 s) of the last boot")
   (TBD "Verify the running image is the one boot-image gives for primary-ok and quick-resets")
