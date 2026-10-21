# Research questions

The platform investigates the following hypotheses without assuming their answers:

1. How do MAE, RMSE and signed bias vary with noise and missing-observation patterns?
2. Can model prediction bridge short missing windows, and when does its age become unsafe?
3. Does observation correction recover after missing values or drift disappears?
4. Does a model-informed state source change violation duration, irrigation input and switching
   relative to direct observation hysteresis under the same exogenous draws?
5. Can remote monitoring fail while the local closed loop continues? How long does the remote
   cache remain stale and how quickly does it resynchronize?
6. When does model mismatch degrade state estimation or closed-loop performance?
7. How sensitive are findings to priors, gain, action delays, fallback horizon and assumed safety bands?

The software can answer questions about its configured simulation, not about the empirical
accuracy of a real greenhouse model or wireless reliability. A useful outcome can be a failure
case, a tie, or a tradeoff between accuracy, environmental violations and control effort.
No novelty or state-of-the-art claim is made. No academic references are included in this initial
release, so there are no unverified paper titles, authors, years or DOI claims.
