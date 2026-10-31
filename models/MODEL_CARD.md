# Model card: dropout risk and return likelihood

Written by `models/make_card.py` from the backtests of `models/train_risk.py` (trained 2026-10-27). Every number below comes from those files. The tool shows this card beside every risk list.

## What the models predict

| Model | For | Predicts | Handbook measure | What the leader does with it |
|---|---|---|---|---|
| Dropout risk | a household interviewed in the last round | not interviewed in this round | loss, the complement of continuation (Box 2.0, Section 3.4.3) | give it an early first dial at its usual hour, keep its enumerator, check its numbers, collect another number |
| Return likelihood | a household interviewed two rounds ago and missed last round | interviewed again within the next three rounds | returns (Sections 3.3.5 and 3.4.3) | order the redials; never drop a household, which the handbook rules out (3.3.5) |

Interviewed means a completed call-log case, as the handbook's build script defines it. A tier is never a prediction about one household: it says how similar households fared.

## Training data

| Program | Rounds used | Round numbers | Cases | Dropout pairs | Return pairs | Number codes | Refusal codes | Call length |
|---|---|---|---|---|---|---|---|---|
| L2CU | 79 | 2–82 | 125,670 | 115,609 | – | yes | no | yes |
| L2T | 15 | 1–17 | 35,679 | 25,387 | – | no | no | yes |
| L2KGZ | 30 | 1–42 | 50,948 | 33,011 | – | no | no | yes |
| L2Kaz | 32 | 1–33 | 58,272 | 44,489 | – | yes | yes | yes |
| L2PHL | 9 | 2–10 | 22,055 | 9,378 | 1,405 | yes | yes | yes |
| L2Indo | 15 | 1–28 | 68,962 | 12,164 | 1,675 | yes | yes | no |

The handbook's harmonized case and dial tables of its six programs with dial logs, kept locally and never published. Loss rate over all dropout pairs: 5.0%; return rate over all return pairs: 46.6%. The return model uses L2PHL and L2Indo only, because they redial almost every missed household; elsewhere the households redialed are chosen, and a model would learn the team's choice rather than the household's chance (3.3.5). Training writes only coefficients and the aggregates below, with no household ID and with cells under 10 suppressed.

## Features

Operational only: no demographic feature. Each is computed from what is known before the round predicted.

| Dropout model | Coefficient | 95% interval | z | p | Mean | SD |
|---|---|---|---|---|---|---|
| Joined in the round before | +0.282 | +0.263 to +0.300 | 29.5 | <0.001 | 0.07 | 0.25 |
| Joined two rounds before | +0.131 | +0.114 to +0.148 | 15.1 | <0.001 | 0.05 | 0.21 |
| Joined three rounds before | +0.074 | +0.057 to +0.091 | 8.7 | <0.001 | 0.04 | 0.20 |
| In the panel 7 to 12 rounds | -0.060 | -0.086 to -0.034 | -4.6 | <0.001 | 0.17 | 0.38 |
| In the panel 13 rounds or more | -0.377 | -0.411 to -0.343 | -21.7 | <0.001 | 0.56 | 0.50 |
| Rounds missed among the three before | +0.203 | +0.185 to +0.221 | 22.7 | <0.001 | 0.05 | 0.31 |
| Missed the round before | +0.020 | +0.003 to +0.036 | 2.3 | 0.019 | 0.02 | 0.13 |
| Dials needed last round (log) | +0.264 | +0.235 to +0.294 | 17.5 | <0.001 | 1.24 | 0.60 |
| Days needed last round | +0.110 | +0.088 to +0.132 | 9.8 | <0.001 | 1.72 | 1.43 |
| Same enumerator in the last two interviews | -0.092 | -0.114 to -0.070 | -8.2 | <0.001 | 0.79 | 0.41 |
| Last round's first dial within an hour of the interview before | -0.031 | -0.057 to -0.006 | -2.4 | 0.016 | 0.20 | 0.40 |
| Last interview at 18:00 or later | +0.019 | -0.002 to +0.040 | 1.8 | 0.080 | 0.20 | 0.40 |
| Last interview before 12:00 | -0.034 | -0.057 to -0.012 | -3.0 | 0.003 | 0.24 | 0.42 |
| Length of the last interview (minutes) | +0.010 | -0.011 to +0.030 | 0.9 | 0.351 | 13.08 | 7.83 |
| A number not working or switched off last round | +0.029 | +0.005 to +0.053 | 2.3 | 0.020 | 0.09 | 0.29 |
| A refusal last round before the interview | -0.015 | -0.034 to +0.004 | -1.5 | 0.130 | 0.02 | 0.12 |


| Return model | Coefficient | 95% interval | z | p | Mean | SD |
|---|---|---|---|---|---|---|
| Joined in the round before the miss | -0.408 | -0.516 to -0.299 | -7.3 | <0.001 | 0.32 | 0.47 |
| Joined two rounds before the miss | -0.223 | -0.315 to -0.132 | -4.8 | <0.001 | 0.11 | 0.31 |
| Joined three rounds before the miss | -0.077 | -0.168 to +0.014 | -1.6 | 0.098 | 0.18 | 0.38 |
| In the panel 7 to 12 rounds | -0.027 | -0.106 to +0.051 | -0.7 | 0.494 | 0.05 | 0.22 |
| In the panel 13 rounds or more | -0.307 | -0.402 to -0.213 | -6.4 | <0.001 | 0.09 | 0.28 |
| Rounds missed among the three before the last interview | -0.207 | -0.296 to -0.119 | -4.6 | <0.001 | 0.27 | 0.60 |
| Dialed in the missed round | -0.049 | -0.144 to +0.046 | -1.0 | 0.315 | 0.99 | 0.08 |
| Dials in the missed round (log) | -0.130 | -0.307 to +0.047 | -1.4 | 0.150 | 2.08 | 0.68 |
| Days dialed in the missed round | -0.294 | -0.483 to -0.106 | -3.1 | 0.002 | 5.25 | 3.08 |
| Reached in the missed round, no interview | +0.147 | +0.070 to +0.223 | 3.7 | <0.001 | 0.35 | 0.48 |
| A refusal in the missed round | -0.100 | -0.177 to -0.023 | -2.5 | 0.011 | 0.10 | 0.30 |
| A number not working or switched off in the missed round | +0.028 | -0.082 to +0.138 | 0.5 | 0.621 | 0.47 | 0.50 |
| Dials needed at the last interview (log) | -0.017 | -0.097 to +0.063 | -0.4 | 0.681 | 1.54 | 0.63 |
| Missed round first dialed by the enumerator of the last interview | +0.026 | -0.088 to +0.140 | 0.5 | 0.655 | 0.61 | 0.49 |

Significance (`models/coef_significance.py`): standard errors from the sandwich estimator of the same penalised fit, with households as clusters, since a household contributes several household-rounds (240,038 household-rounds from 18,152 households for dropout; 3,080 from 2,550 for return). z is the coefficient over its standard error; p is two-sided. With this many household-rounds, small effects reach significance: the size of a coefficient and the backtests below say more about the lists than p does. Features are correlated (the tenure bands, the missed rounds), so each coefficient is the feature's effect with the others held fixed. 95% intervals that include zero: dropout, last interview at 18:00 or later, length of the last interview (minutes), a refusal last round before the interview; return, joined three rounds before the miss, in the panel 7 to 12 rounds, dialed in the missed round, dials in the missed round (log), a number not working or switched off in the missed round, dials needed at the last interview (log), missed round first dialed by the enumerator of the last interview.


Coefficients are per standard deviation, from a ridge-penalised logistic regression with one intercept per program. Rounds since joining is compared with 4 to 6 rounds. A feature a program's codes do not define counts as average for that program. In the tool, the explanation adds up the contributions of related features and describes the household's own values.

**Left out on purpose:** household size, the respondent's sex and age, education, region, urban or rural, language, and every survey answer. Region and urban or rural are sampling variables, but they would steer effort by place; survey answers would steer it by welfare. The leader view shows how each tier divides by stratum, so that any concentration in one area is visible.

**Not in the training tables:** the number of phone numbers and whether another number was used. The tool records both, so a program can add them once its own data allow a refit.

## How well they work, on data they were not trained on

### Dropout risk, each program left out in turn

Trained on five programs, tested on the sixth with the average intercept: the honest test for a new program such as Mongolia.

| Program left out | Household-rounds | Loss rate | AUC | AUC, tenure only | AUC, dials rule | AUC, boosted trees | Brier / no model | Losses in the high tier | … tenure only |
|---|---|---|---|---|---|---|---|---|---|
| L2CU | 115,609 | 1.0% | 0.72 | 0.64 | 0.60 | 0.72 | 0.0107 / 0.0099 | 41% | 29% |
| L2T | 25,387 | 6.8% | 0.75 | 0.67 | 0.58 | 0.74 | 0.0607 / 0.0633 | 42% | 31% |
| L2KGZ | 33,011 | 3.0% | 0.72 | 0.63 | 0.61 | 0.71 | 0.0285 / 0.0293 | 44% | 30% |
| L2Kaz | 44,489 | 9.1% | 0.75 | 0.70 | 0.59 | 0.71 | 0.0813 / 0.0830 | 35% | 24% |
| L2PHL | 9,378 | 22.9% | 0.72 | 0.59 | 0.58 | 0.65 | 0.1795 / 0.1766 | 29% | 26% |
| L2Indo | 12,164 | 15.3% | 0.69 | 0.60 | 0.57 | 0.65 | 0.1373 / 0.1299 | 31% | 21% |

AUC is the chance that a lost household scores above a kept one (0.5 is no better than chance). The high tier is the top 15% of each round's households. The two baselines: the loss rate by rounds since joining alone (the handbook's hazard curve), and the rule "needed more dials than three households in four last round". The boosted trees are a check on the model's form. They ranked households no better than the logistic model in any program (AUC); their chances were somewhat closer to what happened in L2CU, L2Kaz, L2PHL, L2Indo (Brier), which bears on calibration, and the tool recalibrates chances on the program's own rounds before showing any. The logistic model, whose explanations are clearer, is the one used.

### Dropout risk, with the program's own past rounds

Rolling origin: at each round, only the rounds whose outcomes were already known are used. "Recalibrated" here is the model trained on the other five programs, with its intercept and slope refitted on the program's own past rounds once two rounds have outcomes. The tool does the same for a new program with the model trained on all six.

| Program | Rounds tested | AUC, own rounds only | AUC, recalibrated | Brier, recalibrated / as is | Losses in the high tier | High tier: loss rate (95% CI) | Medium tier | Low tier |
|---|---|---|---|---|---|---|---|---|
| L2CU | 75 | 0.74 | 0.74 | 0.0095 / 0.0099 | 42% | 2.7% (2.5%–2.9%) | 1.0% (0.9%–1.1%) | 0.4% (0.4%–0.5%) |
| L2T | 11 | 0.73 | 0.74 | 0.0515 / 0.0524 | 49% | 18.8% (17.5%–20.2%) | 5.2% (4.8%–5.7%) | 2.3% (2.0%–2.6%) |
| L2KGZ | 20 | 0.72 | 0.71 | 0.0262 / 0.0261 | 46% | 8.5% (7.7%–9.3%) | 2.7% (2.4%–3.0%) | 1.1% (0.9%–1.3%) |
| L2Kaz | 28 | 0.75 | 0.74 | 0.0734 / 0.0770 | 37% | 21.2% (20.2%–22.2%) | 9.2% (8.8%–9.7%) | 4.4% (4.1%–4.7%) |
| L2PHL | 6 | 0.72 | 0.73 | 0.1568 / 0.1761 | 30% | 46.0% (43.0%–49.0%) | 31.1% (29.3%–33.0%) | 9.7% (8.8%–10.7%) |
| L2Indo | 7 | 0.68 | 0.67 | 0.1126 / 0.1200 | 34% | 30.2% (27.8%–32.6%) | 15.2% (14.0%–16.5%) | 6.8% (6.1%–7.6%) |

### Return likelihood

| Program tested | Household-rounds | Return rate | AUC, trained on the other | AUC, tenure only | Brier / no model | AUC, recalibrated on own rounds | Brier recalibrated / no model | High tier: return rate, trained on the other | Low tier (all but the high tier), trained on the other |
|---|---|---|---|---|---|---|---|---|---|
| L2PHL | 1,405 | 59.1% | 0.61 | 0.55 | 0.3916 / 0.2418 | 0.59 | 0.2326 / 0.2376 | 74.5% (68.2%–80.0%) | 56.4% (53.6%–59.2%) |
| L2Indo | 1,675 | 36.1% | 0.60 | 0.57 | 0.3738 / 0.2306 | 0.62 | 0.2254 / 0.2272 | 52.2% (46.0%–58.4%) | 33.3% (30.9%–35.7%) |

## Where the models do poorly

- **Levels do not carry between programs.** Loss rates range from 1.0% to 22.9%. Applied as it is to a program it has not seen, the dropout model ranks households usefully but its chances are off: in three of the six programs its Brier score is worse than having no model. The tool therefore shows a new program only the tier and how far a household is above the round's average, and shows a chance only after recalibrating on the program's own rounds.
- **The ranking is moderate, not sharp.** The weakest held-out program is L2Indo (AUC 0.69). The high tier holds between 29% and 49% of next round's losses; most losses still come from the medium and low tiers.
- **The return model is weak.** Its AUC is about 0.6 within a program (L2PHL 0.59, L2Indo 0.62 after recalibration), and recalibrated it is only slightly better than the average return rate. Its return levels differ so much between L2PHL and L2Indo that pooling the two inverts the ranking. Use it only to order redials, never to decide whom to drop.
- **Some features are missing in some programs.** L2T's and L2KGZ's result codes are not defined in the handbook, so the number and refusal features rest on the other programs; L2Indo records no call length.
- **Rounds since joining counts from the first round in the data.** A program that starts using the tool mid-panel undercounts its households' tenure until earlier rounds are loaded.
- **Dropout also depends on next round's effort,** which no model fitted before the round can see.

## How the tool uses them

- **Tiers, tied to workload.** Within the round, the top 15% of households by score are high, the next 35% medium, the rest low. The dropout model keeps high, medium, low: no two adjacent tiers' 95% intervals overlapped in any held-out test of the model as trained or recalibrated. For the return model the medium and low tiers overlapped in L2PHL's rolling-origin test of the recalibrated model (60.5% and 57.0%), so its tiers are merged to high and low, the low tier taking the rest. The program-only refit is tested separately, on the program's own rounds, before the tool offers it.
- **Leader only.** Enumerators never see a household's tier. The tier is not written into assignment files; it only moves high tier households earlier in the plan of first dials, as Section 3.4's box asks.
- **Features behind the score.** The three groups of features that move the score most, with the household's own values.
- **The program's own data.** After two rounds with outcomes, the tool offers a recalibration, backtested on the program's own rounds; after about 300 own losses, a refit. The leader switches only after seeing the backtest, and the card says which version is active.
