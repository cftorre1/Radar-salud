# Model quality experiment V1 — staging only

Date: 27 September 2026 (Santiago)  
Candidate: a1256d1a2b3fea9ed9bc9ef0860f77eeb976dbe3  
Run: https://github.com/cftorre1/Radar-salud/actions/runs/36365445785  
Staging QA / Reviewer / preview: https://github.com/cftorre1/Radar-salud/actions/runs/36365445983

## Scope and method

One blind comparison ran the same structured evidence and output contract through Luna, Terra and Astra for five tasks: local news summary, complex report analysis, multi-source Chile synthesis, a high-value FREE insight from three independent SIS signals, and a useful FREE Global teaser. The eight-piece corpus combines one Minsal news item, three SIS normative signals, the WHO workforce report and Reuters context, plus Deloitte and PwC material on AI in health. The source IDs, exact prompts and blinded outputs are in the corpus artifact.

Quality used the approved 100-point rubric: fidelity 25; selection/prioritization 20; synthesis/connection 20; Chile value 20; executive utility 15. Scoring was blind; the model mapping was opened after scores were recorded. Every one of the 15 responses returned valid JSON with source references limited to the evidence provided. Manual review found no material factual error or unsupported claim. Estimated remaining edit time is editorial judgment, not measured time. One Luna teaser needs a global-survey qualifier before publication.

## Blinded scores and model mapping

| Model | simple news | complex report | multisource Chile | FREE feature | Global teaser | Mean |
|---|---:|---:|---:|---:|---:|---:|
| Astra | 82 | 91 | 93 | 91 | 90 | 89.4 |
| Luna | 86 | 94 | 98 | 94 | 91 | 92.6 |
| Terra | 82 | 96 | 92 | 93 | 91 | 90.8 |

Luna led on the multisource, FREE-feature and teaser cases. Terra led on the complex report case. Astra did not lead any case. The five samples are directional only.

## Observed API usage

| Model | Input tokens | Output tokens | Cost estimate | Mean latency |
|---|---:|---:|---:|---:|
| Luna | 4,060 | 2,909 | $0.004302 | 7.0 s |
| Terra | 4,060 | 2,034 | $0.032528 | 4.8 s |
| Astra | 4,060 | 2,147 | $0.147950 | 9.9 s |
| **Total** | **12,180** | **7,090** | **$0.184780** | — |

The seven-day estimate moved from $0.032416 to $0.217196, below the authorized $10/week ceiling. Astra was accessible. Costs use observed Responses API token counts and standard list rates; they are not a billing statement. Astra's standard rate was added to the fail-closed estimator from the official OpenAI pricing table: https://developers.openai.com/api/docs/pricing

## Business case

A “report” below means one complex-report-analysis output at the observed per-case token volume.

| Route | Cost / complex report | 10 reports/month | 15 reports/month |
|---|---:|---:|---:|
| Luna-only | $0.000961 | $0.009610 | $0.014415 |
| Terra deep analysis | $0.006480 | $0.064800 | $0.097200 |
| Astra for complex reports | $0.030040 | $0.300400 | $0.450600 |

For one five-case package (news, report, multisource, FREE feature, teaser), observed counterfactual estimates are: Luna-only $0.004302; Luna for simple news/teaser plus Terra for the other three $0.021678; Terra-only $0.032528; Terra default plus Astra for report/FREE feature $0.085432. At 10/15 packages per month those routes cost $0.043/$0.065, $0.217/$0.325, $0.325/$0.488 and $0.854/$1.281, respectively.

On the single complex-report case, Terra scored 2 points above Luna for $0.005519 more per output (about $0.00276 per observed score point); Astra scored 5 points below Terra while costing $0.023560 more. These are single-case comparisons, not stable marginal-value estimates. No manual-production baseline was measured, so human minutes saved remain unavailable.

## Recommendation and limits

Keep the current production routing unchanged. This sample does not justify a product routing change or recurring spend increase. For further evidence, repeat each task category with several distinct documents and have a second reviewer score the blind outputs. Do not publish experimental output automatically. The complex-report case used Alicanto's stored structured analysis of the WHO report, not its full 60-page text; a future document-ingestion comparison should test the full source when access and extraction are available.

No changes were made to main/production, pricing, product routing, editorial rules, or recency rules.
