# opencycle — Demo Checklist

**Estimated duration:** 2m 55s

## Before presenting
- [ ] Run and test the demo before judging begins.
- [ ] Have a backup screenshot or short recording ready.
- [ ] Confirm all claims in the pitch can be explained by the team.
- [ ] Repository: https://github.com/synthetic/opencycle

## Demo flow

### 1. Open the project and show its main user-facing entry point.
- **Show:** The audience can see where a user interacts with the project.
- **Say:** Explain the user journey before showing implementation details.
- **Time:** 25 seconds
- **Check first:** Confirm the application starts and the demo environment is prepared.
- **Evidence basis:** Always included; verify the entry point manually before judging.

### 2. Run one automated test suite, for example `tests/test_rebalancer.py`.
- **Show:** Judges see automated verification the team can reproduce.
- **Say:** Explain what the test covers and, just as importantly, what it does not cover.
- **Time:** 25 seconds
- **Check first:** Run the tests before the event and confirm they pass in the demo environment.
- **Evidence basis:** Test file `tests/test_rebalancer.py` was inspected; passing status not verified by HackPack.

### 3. Demonstrate one core user flow from input to result.
- **Show:** Show the most important outcome the project currently supports.
- **Say:** Choose a flow that works reliably today. Clearly distinguish implemented functionality from planned work.
- **Time:** 110 seconds
- **Check first:** Prepare test data and rehearse the flow; the generator cannot confirm that runtime behavior works.
- **Evidence basis:** Team-rehearsed flow; not verified from repository evidence alone.

### 4. Close with the current limitation and the next improvement.
- **Show:** The judges understand the current scope and realistic next step.
- **Say:** Be direct about what has and has not been validated.
- **Time:** 15 seconds
- **Evidence basis:** Presentation structure, not a repository claim.

## Backup plan

If the live demo fails, show a prepared screenshot or recording and explain the intended flow without claiming a successful live run.
