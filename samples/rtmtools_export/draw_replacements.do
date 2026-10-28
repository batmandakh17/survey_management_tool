* Step 7 of the interview tool: a real rtmtools export of a phone-sample draw with reserves.
* Synthetic frame: 12 PSUs x 15 households, 9-digit numeric household IDs (the Mongolia example's form).
* The installed rtmtools is used, as a task team would use it; the run folder goes to rtm_exports/ in the
* working folder. selection.csv, draw_summary.csv and manifest.json next to this file come from the run of
* 28 October 2026 (rtmtools 0.6.1 with the full-width ID export of 27 October; Stata 18).
* tests/test_rtmtools_import.py reads them into the leader view.
clear all
set more off
which rtmsample_draw
set obs 180
gen int psu = 1101 + floor((_n - 1) / 15)
gen int k = mod(_n - 1, 15) + 1
gen long hhid = psu * 100000 + k
format hhid %12.0f
gen byte region = 1 + (psu > 1106)
rtmsample draw, n(8) strata(psu) reserve(3) generate(s) id(hhid) seed(20261028)
tab s_sel
tab s_reserve
list hhid psu s_sel s_reserve s_order in 1/15, clean
