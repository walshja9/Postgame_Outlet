# PGO table fit

Goal: fit the PGO tables inside the desktop page without shrinking text or hiding results.

The shared table rule prevents cells from wrapping. When a table container is at least 680 pixels wide, allow text to wrap and reduce cell padding from 9 pixels to 8 vertically and 6 horizontally. Keep header words intact and release the availability table's 900-pixel minimum at these widths. Smaller containers retain the existing readable, horizontally scrollable tables. Reuse the existing CSS container sizing in the current PGO board and Forecast Lab, including their archived editions; no new scripts or data calculations.

- [x] Measure the existing weekly table: 1,394 pixels of content in a 1,088-pixel container.
- [x] Prototype shared wrapping and confirm the main PGO tables fit that desktop width.
- [x] Verify the board at 1,226, 980, 800, 375 and 320 pixels; verify Forecast Lab, expanded explanations and comparison tables. Desktop table content fits its container; phone scrolling remains within the table.
- [x] Run the existing presentation checks and regenerate both pages. Final focused checks: 17 passed; the earlier presentation run passed 24 checks. Both pages contain the final shared CSS.

Publish through the existing board and Pages workflows, preserving newer scheduled season snapshots. Record final deployment and public-page checks in the release receipt.

This changes presentation only. Original forecasts, confidence points, grades, model inputs and archived evidence remain intact.
