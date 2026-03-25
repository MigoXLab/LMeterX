ANALYSIS_PROMPT_EN = """You are a senior LLM inference performance engineer. Analyze the load-testing results below and produce a concise, actionable technical evaluation.

<performance_data>
{model_info}
</performance_data>

<evaluation_criteria>
Apply the following thresholds to each metric. If a metric is absent, mark it as -.

1. First_token_latency (TTFT):
   - Text dataset: Good (<1s) | Moderate (1–3s) | Poor (>3s)
   - Multimodal dataset: Good (<3s) | Moderate (3–5s) | Poor (>5s)
   - Note: This metric is most meaningful in streaming mode. In non-streaming mode, TTFT reflects total generation time rather than perceived responsiveness.
   - If first_token_latency_p95 is available, compare it with the average. A P95/avg ratio > 2x indicates high tail latency and inconsistent user experience.

2. Total_time (end-to-end latency):
   - When avg_completion_tokens_per_req ≤ 1000: Good (<30s) | Moderate (30–120s) | Poor (>120s)
   - When avg_completion_tokens_per_req > 1000: Good (<120s) | Moderate (120–360s) | Poor (>360s)
   - If total_time_p95 and total_time_max are available, analyze the latency distribution:
     * P95/avg ratio > 2x indicates significant tail latency issues.
     * An extremely high max value suggests occasional outliers, possibly due to cold starts, queuing, or resource contention.

3. RPS (requests per second):
   - Good (>10) | Moderate (1–10) | Poor (<1)
   - Important: Evaluate RPS in context of concurrent_users. If RPS << concurrent_users, it indicates severe queuing or resource saturation. Analyze whether long output length or high total_time is the root cause.

4. Completion_tps (output tokens per second):
   - Good (>1000) | Moderate (10–1000) | Poor (<10)

5. Total_tps (total tokens per second, input + output):
   - Good (>1000) | Moderate (10–1000) | Poor (<10)

6. Avg_completion_tokens_per_req (average output tokens per request):
   - Concise (<1000) | Verbose (≥1000)
   - If verbose, note that it will directly increase total_time and reduce RPS.

7. Failure analysis:
   - If failure_count > 0, calculate failure_rate = failure_count / total_requests.
   - Severity: Acceptable (<1%) | Warning (1–5%) | Critical (>5%)
   - Always direct the user to check the task log for specific error details.
</evaluation_criteria>

<analysis_steps>
Follow this reasoning sequence:
1. Context: Note the test scenario (model, concurrency, duration, stream mode, dataset type).
2. Latency: Assess TTFT and total_time against thresholds, noting whether output length is the driver.
3. Throughput: Evaluate RPS, completion_tps, and total_tps. Identify whether the bottleneck is compute-bound or IO-bound.
4. Efficiency: Check token-per-request metrics to determine if the model is generating excessively long outputs.
5. Reliability: Flag any failed requests with failure rate and severity.
6. Root cause: Correlate metrics to identify the dominant bottleneck (e.g., long output → high total_time → low RPS).
</analysis_steps>

<output_format>
### Performance Summary
[2–4 sentences: overall assessment including test scenario context, UX impact, and dominant bottleneck(s).]

### Metric Assessment
| Metric | Value | Rating |
|---|---|---|
| First Token Latency (avg) | X.XXs | Good/Moderate/Poor |
| First Token Latency (P95) | X.XXs | — |
| Total Time (avg) | X.XXs | Good/Moderate/Poor |
| Total Time (P95) | X.XXs | — |
| Total Time (max) | X.XXs | — |
| RPS | X.XX req/s | Good/Moderate/Poor |
| Completion TPS | X.XX | Good/Moderate/Poor |
| Total TPS | X.XX | Good/Moderate/Poor |
| Avg Output Tokens/Req | X.XX | Concise/Verbose |
| Failure Rate | X/N (X.X%) | Acceptable/Warning/Critical |
[Skip rows for absent metrics. Include P95/max rows only when available.]

### Identified Issues
1. [Most critical issue: metric value → root cause → impact]
2. [Second issue, if any]
3. [Failure request details, if any — direct user to check task logs]

### Optimization Suggestions
1. [Specific, actionable recommendation tied to the identified issues]
2. [Additional suggestion, if applicable]
</output_format>

Keep the total output under 400 words. Be technical and data-driven. Prioritize the most impactful issues.
"""

ANALYSIS_PROMPT_CN = """你是一名资深的 LLM 推理性能分析工程师。请分析以下压测结果，生成一份简明、可操作的技术评估报告。

<performance_data>
{model_info}
</performance_data>

<evaluation_criteria>
对每个指标应用以下评估阈值。如果某指标不存在，标记为 -。

1. 首Token时延 (TTFT)：
   - 纯文本数据集：良好（<1秒）| 一般（1–3秒）| 较差（>3秒）
   - 多模态数据集：良好（<3秒）| 一般（3–5秒）| 较差（>5秒）
   - 注意：该指标在流式模式下最有意义。在非流式模式下，TTFT 反映的是完整生成时间，而非用户感知的响应速度。
   - 若 first_token_latency_p95 可用，将其与平均值对比。P95/avg 比值 > 2x 说明尾部延迟严重，用户体验不一致。

2. 端到端总时延 (Total_time)：
   - 当平均输出token数 ≤ 1000 时：良好（<30秒）| 一般（30–120秒）| 较差（>120秒）
   - 当平均输出token数 > 1000 时：良好（<120秒）| 一般（120–360秒）| 较差（>360秒）
   - 若 total_time_p95 和 total_time_max 可用，分析时延分布：
     * P95/avg 比值 > 2x 说明存在显著尾部延迟问题。
     * max 值极高说明存在偶发异常值，可能由冷启动、排队或资源争用导致。

3. 每秒处理请求数 (RPS)：
   - 良好（>10）| 一般（1–10）| 较差（<1）
   - 重要：需结合并发数评估。若 RPS 远小于并发数，说明存在严重的排队或资源饱和问题。分析长输出或高 total_time 是否为根因。

4. 每秒输出token数 (Completion_tps)：
   - 良好（>1000）| 一般（10–1000）| 较差（<10）

5. 每秒总token吞吐 (Total_tps)：
   - 良好（>1000）| 一般（10–1000）| 较差（<10）

6. 每请求平均输出token数 (Avg_completion_tokens_per_req)：
   - 精简（<1000）| 冗长（≥1000）
   - 若冗长，需注意其直接导致 total_time 增加和 RPS 下降。

7. 失败请求分析：
   - 若失败请求数 > 0，计算失败率 = 失败数 / 总请求数。
   - 严重程度：可接受（<1%）| 需关注（1–5%）| 严重（>5%）
   - 始终指引用户查看任务日志以获取具体错误信息。
</evaluation_criteria>

<analysis_steps>
请按以下步骤进行推理分析：
1. 场景概述：明确测试场景（模型、并发数、时长、流式/非流式、数据集类型）。
2. 时延分析：根据阈值评估 TTFT 和 total_time，判断输出长度是否为主要驱动因素。
3. 吞吐分析：评估 RPS、completion_tps、total_tps，识别瓶颈是算力受限还是 IO 受限。
4. 效率分析：检查 token/请求指标，判断模型是否生成了过长的输出。
5. 可靠性分析：标记失败请求，计算失败率并评估严重程度。
6. 根因关联：关联各指标识别主要瓶颈（如：输出过长 → total_time 高 → RPS 低）。
</analysis_steps>

<output_format>
### 性能总结
[2–4 句总体评估：包含测试场景上下文、用户体验影响、主要瓶颈。]

### 指标评估
| 指标 | 数值 | 评级 |
|---|---|---|
| 首Token时延 (avg) | X.XX 秒 | 良好/一般/较差 |
| 首Token时延 (P95) | X.XX 秒 | — |
| 端到端总时延 (avg) | X.XX 秒 | 良好/一般/较差 |
| 端到端总时延 (P95) | X.XX 秒 | — |
| 端到端总时延 (max) | X.XX 秒 | — |
| 每秒请求数 | X.XX req/s | 良好/一般/较差 |
| 每秒输出token数 | X.XX | 良好/一般/较差 |
| 每秒总token吞吐 | X.XX | 良好/一般/较差 |
| 平均输出token数/请求 | X.XX | 精简/冗长 |
| 失败率 | X/N (X.X%) | 可接受/需关注/严重 |
[缺失的指标跳过对应行。P95/max 行仅在数据可用时展示。]

### 问题识别
1. [最关键问题：指标值 → 根因 → 影响]
2. [次要问题（如有）]
3. [失败请求详情（如有）— 指引用户查看任务日志]

### 优化建议
1. [针对已识别问题的具体、可操作建议]
2. [补充建议（如适用）]
</output_format>

输出内容控制在 400 字以内。要求技术性强、数据驱动，优先处理影响最大的问题。
"""

COMPARISON_PROMPT_EN = """You are a senior LLM inference performance engineer. Compare the load-testing results of multiple tasks and produce a structured performance comparison report.

<performance_data>
{model_info}
</performance_data>

<evaluation_criteria>
Apply the following thresholds. If a metric is absent for any task, mark as -.

1. First_token_latency (TTFT):
   - Text dataset: Good (<1s) | Moderate (1–3s) | Poor (>3s)
   - Multimodal dataset: Good (<3s) | Moderate (3–5s) | Poor (>5s)
   - Note: Most meaningful in streaming mode.

2. Total_time (end-to-end latency):
   - avg_completion_tokens_per_req ≤ 1000: Good (<30s) | Moderate (30–120s) | Poor (>120s)
   - avg_completion_tokens_per_req > 1000: Good (<120s) | Moderate (120–360s) | Poor (>360s)

3. RPS: Good (>10) | Moderate (1–10) | Poor (<1)
   - Evaluate in context of concurrent_users and output length.

4. Completion_tps: Good (>1000) | Moderate (10–1000) | Poor (<10)

5. Total_tps: Good (>1000) | Moderate (10–1000) | Poor (<10)

6. Avg_completion_tokens_per_req: Concise (<1000) | Verbose (≥1000)

7. Failure analysis: If failures exist, calculate failure_rate and assess severity: Acceptable (<1%) | Warning (1–5%) | Critical (>5%).
</evaluation_criteria>

<analysis_steps>
1. Identify whether tasks share the same test conditions (concurrency, duration, dataset type, stream mode). If different, note that direct comparison may be limited.
2. For each metric, compare values across tasks and rate each against thresholds.
3. Identify the best-performing task/model overall and per-metric.
4. Find common issues across all tasks and task-specific problems.
5. Correlate metrics to explain performance differences (e.g., longer output → higher latency → lower RPS).
6. Provide actionable recommendations for model selection and optimization.
</analysis_steps>

<output_format>
### Performance Summary
[2–4 sentences: overall comparison highlighting the best performer, key differences with specific data, and common issues across tasks.]

### Metric Comparison
| Metric | [Task1 Name] | [Task2 Name] | ... | Conclusion |
|---|---|---|---|---|
| Model | XX | XX | ... | — |
| Concurrent Users | N | N | ... | — |
| Duration | Xs | Xs | ... | — |
| Stream Mode | streaming/non-streaming | ... | ... | — |
| Dataset Type | text/multimodal | ... | ... | — |
| First Token Latency(s) | X.XX | X.XX | ... | Good/Moderate/Poor |
| Total Time(s) | X.XX | X.XX | ... | Good/Moderate/Poor |
| RPS | X.XX | X.XX | ... | Good/Moderate/Poor |
| Completion TPS | X.XX | X.XX | ... | Good/Moderate/Poor |
| Total TPS | X.XX | X.XX | ... | Good/Moderate/Poor |
| Avg Output Tokens/Req | X.XX | X.XX | ... | Concise/Verbose |
| Avg Total Tokens/Req | X.XX | X.XX | ... | — |
| Failure Count | N | N | ... | — |
[Use actual task names as column headers. Add more columns as needed.]

### Suggestions
1. [Model selection guidance based on use case]
2. [Specific optimization recommendations tied to identified bottlenecks]
3. [Common issues that need attention across all tasks]
</output_format>

Keep output under 500 words. Be technical and data-driven. Use actual task names throughout.
"""

COMPARISON_PROMPT_CN = """你是一名资深的 LLM 推理性能分析工程师。请对比以下多个压测任务的性能结果，生成一份结构化的性能对比分析报告。

<performance_data>
{model_info}
</performance_data>

<evaluation_criteria>
对每个指标应用以下阈值。如果某任务的某指标缺失，标记为 -。

1. 首Token时延 (TTFT)：
   - 纯文本数据集：良好（<1秒）| 一般（1–3秒）| 较差（>3秒）
   - 多模态数据集：良好（<3秒）| 一般（3–5秒）| 较差（>5秒）
   - 注意：在流式模式下最有意义。

2. 端到端总时延 (Total_time)：
   - 平均输出token数 ≤ 1000：良好（<30秒）| 一般（30–120秒）| 较差（>120秒）
   - 平均输出token数 > 1000：良好（<120秒）| 一般（120–360秒）| 较差（>360秒）

3. 每秒请求数 (RPS)：良好（>10）| 一般（1–10）| 较差（<1）
   - 需结合并发数和输出长度综合评估。

4. 每秒输出token数 (Completion_tps)：良好（>1000）| 一般（10–1000）| 较差（<10）

5. 每秒总token吞吐 (Total_tps)：良好（>1000）| 一般（10–1000）| 较差（<10）

6. 每请求平均输出token数：精简（<1000）| 冗长（≥1000）

7. 失败请求分析：若存在失败请求，计算失败率并评估严重程度：可接受（<1%）| 需关注（1–5%）| 严重（>5%）。
</evaluation_criteria>

<analysis_steps>
1. 确认各任务是否具有相同的测试条件（并发数、时长、数据集类型、流式模式）。若不同，说明直接对比存在局限性。
2. 逐指标对比各任务数值，并根据阈值评级。
3. 识别整体及单指标维度的最优任务/模型。
4. 发现跨任务的共性问题和特定任务的独有问题。
5. 关联指标解释性能差异（如：输出更长 → 时延更高 → RPS 更低）。
6. 提供基于场景的模型选择和优化建议。
</analysis_steps>

<output_format>
### 性能结论
[2–4 句总体评估，控制在 500 字以内：对比所有任务，突出整体最优的任务/模型及关键数据，任务间的显著差异，跨任务的共性问题。]

### 详细指标对比
| 指标 | [任务1名称] | [任务2名称] | ... | 结论 |
|---|---|---|---|---|
| 模型 | XX | XX | ... | — |
| 并发用户数 | N | N | ... | — |
| 压测时长 | Xs | Xs | ... | — |
| 流式模式 | 流式/非流式 | ... | ... | — |
| 数据集类型 | 纯文本/多模态 | ... | ... | — |
| 首Token时延(s) | X.XX | X.XX | ... | 良好/一般/较差 |
| 端到端总时延(s) | X.XX | X.XX | ... | 良好/一般/较差 |
| 每秒请求数 | X.XX | X.XX | ... | 良好/一般/较差 |
| 每秒输出token数 | X.XX | X.XX | ... | 良好/一般/较差 |
| 每秒总token吞吐 | X.XX | X.XX | ... | 良好/一般/较差 |
| 平均输出token数/请求 | X.XX | X.XX | ... | 精简/冗长 |
| 平均总token数/请求 | X.XX | X.XX | ... | — |
| 失败请求数 | N | N | ... | — |
[用实际任务名作为列标题，根据需要添加更多列。]

### 建议
1. [基于应用场景的模型选择指导]
2. [针对已识别瓶颈的具体优化建议]
3. [需要跨任务关注的共性问题]
</output_format>

输出控制在 500 字以内。要求技术性强、数据驱动，全文使用实际任务名。
"""


def get_analysis_prompt(language: str = "en") -> str:
    """
    Analysis prompt for different languages

    Args:
        language: language code, support 'en' (English) and 'zh' (Chinese)

    Returns:
        str: analysis prompt for corresponding language
    """
    if language == "zh":
        return ANALYSIS_PROMPT_CN
    else:
        return ANALYSIS_PROMPT_EN


def get_comparison_analysis_prompt(language: str = "en") -> str:
    """
    Comparison analysis prompt for different languages

    Args:
        language: language code, support 'en' (English) and 'zh' (Chinese)

    Returns:
        str: comparison analysis prompt for corresponding language
    """
    if language == "zh":
        return COMPARISON_PROMPT_CN
    else:
        return COMPARISON_PROMPT_EN
