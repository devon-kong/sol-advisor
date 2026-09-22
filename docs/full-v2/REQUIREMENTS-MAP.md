# Full-v2 requirements and test map

Basis: `SA-FULL-V2-20260920-R1`. Status vocabulary:

> Flow alignment now has 186/186 Python 3.14 discovery and 19 current Python 3.12
> integration checks. Current receipts and review status live under
> `.agent-artifacts/20260922-flow-alignment/archive/`. The mapping below is historical
> unless explicitly qualified by this revision; native full-team behavior is not re-proven.

Current revision mapping:

Fresh-review closure R09/R15/R19/R30 evidence is retained in
`.agent-artifacts/20260922-fresh-closure-e38c03/archive/report.md`. It covers corrected-review
identity reuse and persisted ancestry through recursive acceptance, stage-selector examples,
and a separately labeled bounded native trial. Native trial outcomes do not replace source
regression or establish general cost, speed or hard-isolation claims.

| Requirements | Current evidence | Boundary |
|---|---|---|
| R02/R05/R27/R28 | `test_flow_alignment_integration`: actual three-stage assembly, immutable stage scope, CLI final acceptance, predecessor rebind refusal | real tools, synthetic runtime identities |
| R07/R13/R14/R16 | early P, missing/failed/optional late E, immutable P, old-log tamper refusal | no extra reviewer for appended evidence |
| R15/R22 | registered probe write/network/read refusal and valid declared read; before/after window and replay tests | macOS child sandbox; native reviewer behavioral only |
| R08/R09 | P2 hard/behavioral design reviews and design/final context separation | design approval never substitutes for V/A |
| R22 | native Sol authored probe, same-context evidence continuation, admitted stage V | bounded prior canary, synthetic Terra identities; predates final contract/read-policy tightening |
| R20/R30 | consistent Root/Sol duties and new P2 usage; mandatory integration IDs in `verify.sh` | production installation untouched |


- `PASS-OFFLINE`: implemented and exercised by source/unit/integration evidence.
- `PASS-NATIVE`: exercised by a fresh native Agent session that explicitly loaded the development
  source; any host-enforcement limitation remains stated in the evidence.
- `PARTIAL-NATIVE`: offline mechanism exists, but required native Agent observation is missing.
- `NOT-RUN`: the required class of evidence was not executed.
- `HISTORICAL_ONLY`: a retained prior-run fact, not acceptance for current bytes.
- `PASS-NATIVE-BOUNDED`: the stated native fixture passed; no claim beyond that fixture.
- `PARTIAL-PERFORMANCE`: the stated timing layer was measured, with another required layer missing.

No `PARTIAL-NATIVE` or `NOT-RUN` row is silently treated as completed evidence.

## Historical solo-correction snapshot (superseded by P2 flow alignment)

`e7dae270…` is a historical `fix-first`. Its later c7b5 candidate had formal
`E-formal-verify-candidate-c7b5` with 135/135 pass, followed by a fresh Sol technical
`fix-first`; formal V admission was unavailable. Its later c23e candidate had formal
`E-formal-verify-candidate-c23e` with 143/143 pass, followed by fresh Sol technical `fix-first`;
formal V admission was unavailable. After the later 74e8 finding and Root's solo correction,
the current worktree has 162/162 local
offline tests and a strict verifier pass, bound to a new whole-worktree candidate manifest under
`.agent-artifacts/20260920-full-v2-01a0be24/archive/metrics/20260922-final-evidence-candidate.json`.
There is no formal E, formal V, or acceptance. R/T `PASS-OFFLINE` rows below mean only current
offline mechanisms. R22/T49/final native V remain `PARTIAL-NATIVE / UNPROVEN`: this
host has no behavioral lifecycle capability and the hard V fixture is not a native Sol review.
Fresh independent review of that exact candidate remains required.

Host boundary: the current host exposes broad reviewer permissions but no Root-controlled
native reviewer lifecycle capable of holding the required dual locks. Behavioral admission is
therefore fail-closed; R22/T49 and any final native V are `PARTIAL-NATIVE / UNPROVEN` until
that host capability exists. Tagged hard-read-only V/DR remains the only new-signature path.

## Historical R01–R32 matrix

| ID | Implementation | Evidence | Status |
|---|---|---|---|
| R01 | Root/full responsibilities in `SKILL.md` and `full-workflow.md` | native full plan/dispatch/acceptance plus trace grader | PASS-NATIVE |
| R02 | stage/dependency contract plus actual `update_plan` use | `full_protocol.py`; live task plan history | PASS-NATIVE |
| R03 | explicit peer selections and exact mechanical assembly | native two-Terra assembly plus workflow fixture | PASS-NATIVE |
| R04 | Terra template says peer/self-contained delivery, no lead | two native peer deliveries; no lead/integrator | PASS-NATIVE |
| R05 | CB/I attribution and combined-candidate review binding | native combination and fresh Sol review; tool tests | PASS-NATIVE |
| R06 | full removes default Root technical rerun; non-full text retained | native full behavior plus non-full fixtures | PASS-NATIVE |
| R07 | critical-first then remaining-scope review contract | native correction reviews 1/2 plus grader | PASS-NATIVE |
| R08 | separate DR and challenge path | current offline tagged DR/V validators; current native design challenge is not observed | PARTIAL-NATIVE / UNPROVEN |
| R09 | design/final separation and fresh correction context | current offline separation/relationship checks | PASS-OFFLINE |
| R10 | Terra self-test/self-review/ordinary correction loop | native implementation/correction deliveries; schema/grader | PASS-NATIVE |
| R11 | cause-grouped findings, preserved red evidence, changed method | convergence docs and retained review history | PASS-OFFLINE |
| R12 | impact surface and unmodified-consumer review rules | native cross-consumer and correction reviews | PASS-NATIVE |
| R13 | immutable run/log/receipt and compact P | current real five-output run-check E/log/receipt chain; T61–T62 | PASS-OFFLINE |
| R14 | separate state, E, P, challenge, V, A identities | P1 relationship and self-binding tests | PASS-OFFLINE |
| R15 | exact candidate/environment/runtime identities | current scoped/harness identity tests | PASS-OFFLINE |
| R16 | applicability-bound evidence and changed-input invalidation | current review/final drift tests | PASS-OFFLINE |
| R17 | compatible scoped candidate optimization | current scoped E→P→V→A legal/drift chain | PASS-OFFLINE |
| R18 | structured error categories and affected-scope failure | `WorkflowError`; tool tests | PASS-OFFLINE |
| R19 | intents/receipts/CAS/process cleanup/no replay | current bootstrap/recovery matrix; T61–T63 | PASS-OFFLINE |
| R20 | full workers load core/owned contract and needed risk methods; Root owns procedure loading | three-pair native loading A/B plus fresh modified-core confirmation | PASS-NATIVE |
| R21 | exact role/model/effort pins and runtime schemas | historical runtime receipts; new attestation pending | HISTORICAL_ONLY |
| R22 | Sol template read-only; Root-side probe publication | tagged hard fixture passes offline; current host behavioral/native lifecycle unavailable | PARTIAL-NATIVE |
| R23 | non-full routes, legacy manifests, installer protections | T01–T03 fresh native one-feature regressions; actual roster/Root checks/Sol review plus independent hidden checks; installer/legacy suite | PASS-NATIVE-BOUNDED / PASS-OFFLINE |
| R24 | unit/integration/fixture/native/performance separated | offline layers are current; hard native V/A and full-route native regression remain unproven | PARTIAL-NATIVE / UNPROVEN |
| R25 | failures included; native tokens measured, price unknown | exact-session token receipts and `metrics.json` | PASS-OFFLINE |
| R26 | no production install/push/business action; rollback docs | repository state and operations guide | PASS-OFFLINE |
| R27 | state gates and exact final candidate/A | current offline final-E/A relation; candidate freeze/review pending | PASS-OFFLINE |
| R28 | byte assembly only; overlaps/semantic merge rejected | workflow tests and grader | PASS-OFFLINE |
| R29 | grouped review policy, no one-finding gate | reviewer contract/convergence | PASS-OFFLINE |
| R30 | docs/templates/scripts/tests/UI checked together | current 162/162 local discovery plus strict verifier; candidate-bound offline only | PASS-OFFLINE |
| R31 | bounded process/retry behavior and unavailable states | native interruption/recovery and capacity refusal plus tests | PASS-NATIVE |
| R32 | no lead/tester/general management role | native peer team plus exact three-role inventory | PASS-NATIVE |

## Historical T01–T60 matrix

| ID | Evidence | Status |
|---|---|---|
| T01 | fresh native solo Root implements/verifies with zero auxiliaries; hidden behavior passes | PASS-NATIVE-BOUNDED |
| T02 | fresh native delegate uses one Luna/max; Root verifies after handoff, no Sol; hidden behavior passes | PASS-NATIVE-BOUNDED |
| T03 | fresh native audit Root implements/verifies then Sol/high reviews exact fixture; no Terra; behavioral read-only only | PASS-NATIVE-BOUNDED |
| T04 | development-source native full protocol runs | PASS-NATIVE |
| T05 | dependency/A closure and state tests | PASS-OFFLINE |
| T06 | two independent delivery Git assembly | PASS-OFFLINE |
| T07 | overlapping/shared ownership rejects or serializes | PASS-OFFLINE |
| T08 | same/parent-child ownership conflict rejection | PASS-OFFLINE |
| T09 | real two-delivery combined candidate reviewed by fresh Sol | PASS-NATIVE |
| T10 | candidate/evidence drift invalidation | PASS-OFFLINE |
| T11 | wrong baseline receive rejection | PASS-OFFLINE |
| T12 | missing records/evidence/attempt rejection | PASS-OFFLINE |
| T13 | post-ready bundle drift rejection | PASS-OFFLINE |
| T14 | exact repeated receive idempotence | PASS-OFFLINE |
| T15 | same attempt/operation changed bytes conflict | PASS-OFFLINE |
| T16 | corrected attempt rebuilt from baseline without double apply | PASS-OFFLINE |
| T17 | stale expected-version CAS rejection | PASS-OFFLINE |
| T18 | responsible Terra corrected the rejected authority-lifecycle candidate | PASS-NATIVE |
| T19 | ordinary implementation vs Root/authority escalation observed and recorded | PASS-NATIVE |
| T20 | P1 same-cause consumer counterexamples | PASS-OFFLINE |
| T21 | adjacent valid neighbors across P1–P3 | PASS-OFFLINE |
| T22 | seven independent Sol findings demonstrated old tests insufficient | PASS-OFFLINE |
| T23 | design challenge history retained; no current-source native design challenge | HISTORICAL_ONLY / UNPROVEN |
| T24 | design challenge and later implementation reviews used different native contexts | HISTORICAL_ONLY |
| T25 | critical fail-fast receipts include remaining scope | PASS-OFFLINE |
| T26 | review 1 declared remaining scope; fresh review 2 completed it | PASS-NATIVE |
| T27 | relationship validators recompute unchanged consumers | PASS-OFFLINE |
| T28 | reviewer contract separates blocker from optional suggestion | PASS-OFFLINE |
| T29 | simpler implementation freedom documented | PASS-OFFLINE |
| T30 | repeated failure changed from single patch to invariant matrix | PASS-OFFLINE |
| T31 | P requires persisted run provenance | current real run-check E/P chain | PASS-OFFLINE |
| T32 | nonzero exit overrides PASS-looking stdout | PASS-OFFLINE |
| T33 | never-started/timeout/incomplete classes | PASS-OFFLINE |
| T34 | TERM/KILL process-group stubborn-child cleanup | PASS-OFFLINE |
| T35 | log write failure/truncation/tamper tests | PASS-OFFLINE |
| T36 | challenge E/CR separate from reviewer loop | PASS-OFFLINE |
| T37 | candidate change during check/review invalidates | current scoped review/final drift neighbors | PASS-OFFLINE |
| T38 | `.agent-artifacts` progress/report exclusion and explicit binding | PASS-OFFLINE |
| T39 | E/P/log/record byte drift rejected | PASS-OFFLINE |
| T40 | harness/environment identity in request/E | current actual harness material/run E tests | PASS-OFFLINE |
| T41 | old whole mode retains HEAD informational semantics | current legacy/whole compatibility tests | PASS-OFFLINE |
| T42 | old selection preserved; scoped policy has new identity | current whole/legacy/scoped selection tests | PASS-OFFLINE |
| T43 | ignored/external/untracked explicit input tests | current candidate explicit-input tests | PASS-OFFLINE |
| T44 | symlink/hardlink/path/output alias tests | current fd/material alias tests | PASS-OFFLINE |
| T45 | same mtime/size changed scoped byte detected | current argv1/declared-material drift tests | PASS-OFFLINE |
| T46 | unchanged large history fixture remeasured with current candidate source; uncertain scope falls back | current warm benchmark and existing exclusion counterexamples; true cold storage unmeasured | PASS-OFFLINE / PARTIAL-PERFORMANCE |
| T47 | artifact/state/receipt recovery and user-change tests | PASS-OFFLINE |
| T48 | real fourth-spawn capacity refusal; no retry/substitution | PASS-NATIVE |
| T49 | actual Terra/Sol role/model/effort/sandbox receipts plus negative fixtures | offline tagged pin/negative fixtures; native lifecycle unavailable | PARTIAL-NATIVE |
| T50 | native `update_plan` used; capability fallback remains tested | PASS-NATIVE |
| T51 | native parallel path ran; capacity refusal did not lower the quality gate | PASS-NATIVE |
| T52 | exact 0.7.3 Terra/Reviewer migration | PASS-OFFLINE |
| T53 | modified/symlink/nonregular/check-only no-write plus explicit-target/no-HOME installer cases | PASS-OFFLINE |
| T54 | 15+15 bounded paired samples plus six invalid-fixture attempts retained; native token receipts measured, price unknown; full-route paired E2E absent | PARTIAL-NATIVE |
| T55 | general non-12306 fixtures and full-v2 traces | PASS-OFFLINE |
| T56 | no install/publish/business side effects; boundaries documented | PASS-OFFLINE |
| T57 | post-c23e strict verifier: dynamic discovery plus required mechanism IDs, five scoped-chain tests and negative cases; no skips or expected failures accepted | PASS-OFFLINE |
| T58 | P0 checked real HEAD/dirty state before isolated worktree | PASS-OFFLINE |
| T59 | argv spaces/newlines/shell metacharacters remain literal | current run-check argv literal tests | PASS-OFFLINE |
| T60 | runtime receipt fields restricted and action traces treated as data | current tagged runtime-field rejection tests | PASS-OFFLINE |
| T61 | same run ID has one creator; canonical request and intent precede child spawn; partial transaction cannot respawn | current `test_run_check.py` creator/recovery tests | PASS-OFFLINE |
| T62 | P/CR/A shared guard rejects missing request, empty logs, nonterminal record, partial/noncanonical receipt | current real-run consumer counterexamples | PASS-OFFLINE |
| T63 | replay rejects a PASS/FAIL label lacking terminal child facts; process group uncertainty stays `incomplete` | current real-run replay and TERM/KILL tests | PASS-OFFLINE |
| T64 | final A accepts/replays real final E, rejects altered E before intent; synthetic E fails closed | current `test_scoped_chain.py` and `test_workflow.py` | PASS-OFFLINE |
| T65 | full worker core/contract loading versus full Root-reference loading, three paired fresh native runs | 6/6 hidden checks, exact source loads and token/elapsed receipts; one-task scope only | PASS-NATIVE |

## Remaining evidence boundaries

Current source acceptance is determined by the exact candidate and external review receipts,
not by the historical PASS labels above. Preserve these remaining boundaries:

1. Final source review and native trial evidence must identify the bytes they actually checked.
   A report or a previous ship never approves later corrections.
2. P2 permits explicitly contracted Root-observed behavioral review. It does not enforce native
   read-only permissions or detect write-then-restore; hard-required tasks need a read-only host.
3. Bounded native examples do not establish general full-route performance. No three-repeat
   0.7.3 versus current end-to-end Root/Terra/Sol cost and wall-clock comparison is available.
4. Candidate timing has first-observed and warm samples, not controlled cold-storage measurements.
   No host-wide cache purge was authorized or performed.
