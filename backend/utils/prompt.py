ANALYSIS_PROMPT_EN = """
    Analyze the performance results: {model_info}, then produce a concise, technical evaluation focused on the metrics below.

    Rules:
    - If a specific metric is not present in the provided {model_info}, skip its assessment and mark as N/A in the table.
    - First_token_latency assessment: For text dataset: Good (<1s), Moderate (1–3s), Poor (>3s); For multimodal dataset: Good (<3s), Moderate (3–5s), Poor (>5s).
    - Total_time assessment: Depends on the output length, the longer the output length, the longer the Total_time. Generally, if the average output token number per request is less than 1000, the Total_time is good (<30s), moderate (30–120s), poor (>120s); if the average output token number per request is greater than 1000, the Total_time is good (<120s), moderate (120–360s), poor (>360s).
    - RPS assessment: Good (>10), Moderate (<10). If RPS is Moderate, please pay attention to whether the average input and output token number per request is large and the Total_time is poor.
    - Completion_tps assessment: Good (>1000), Moderate (<10-1000), Poor (<10).
    - Total_tps assessment: Good (>1000), Moderate (<10-1000), Poor (<10).
    - Avg_completion_tokens/req assessment: Concise (>1000), Verbose (<1000).
    - failure_request: If there is a failed request, please indicate it in the `Identified Issues` and direct the user to check the task log for the specific error information.
    - Keep output under 300 words, technical, and prioritize the most severe issues.

    Required Output Format:
    ### Performance Summary
    [1–3 sentence overall assessment, including UX judgment and the dominant bottleneck(s).]

    ### Key Metrics
    | Metric | Description |Value| Conclusion |
    |---|---|---|---|
    | Concurrent_users |Number of simultaneous users accessing the system	| N | — |
    | Duration |Duration of the test| X.XX | — |
    | Stream_mode |Whether the test is in streaming mode| streaming/non-streaming | — |
    | Dataset_type |Type of dataset used in the test| text/text-image | — |
    | First_token_latency(s) |Time taken to receive the first token| X.XX | Good/Moderate/Poor |
    | Total_time(s) |Total time taken to complete request| X.XX | Good/Moderate/Poor |
    | RPS |Requests processed per second | X.XX | Good/Poor |
    | Completion_tps |Tokens generated per second for completion only| X.XX | Good/Moderate/Poor |
    | Total_tps|Total tokens processed per second (including prompt and completion)| X.XX | Good/Moderate/Poor |
    | Avg_completion_tokens/req |Average number of completion tokens per request| X.XX | Concise/Verbose |
    | Avg_total_tokens/req |Average total tokens (prompt + completion) per request| X.XX | — |
    | Failure_request|Number of failed requests| N | — |

    ### Identified Issues
    1. [Most critical issue with metric value and impact, if any]
    2. [Highlight failure_request, if any]
    """

ANALYSIS_PROMPT_CN = """
    请分析 LLM 压测性能结果：{model_info}，然后针对以下指标和要求生成一份简明的技术评估报告。

    规则：
    - 如果提供的 {model_info} 中不存在某个指标，请跳过该指标的评估，并在表格中标记为 N/A。
    - 首Token时延 评估：对于纯文本数据集任务：良好（<1 秒），中等（1-3秒），较差（>3 秒）；对于多模态数据集任务：良好（<3 秒），中等（3-5 秒），较差（>5 秒）。
    - 端到端总时延 评估：该指标取决于输出长度，输出长度越长，该指标越长。一般来说，如果每个请求的平均输出token数在1000以内，该指标良好（<30 秒），中等（30-120 秒），较差（>120 秒）；如果每个请求的平均输出token数在1000以上，该指标良好（<120 秒），中等（120-360 秒），较差（>360 秒）。
    - 每秒处理的请求数 评估：良好（>10），一般（<10）。如果 每秒处理的请求数 为“一般”，请重点关注是不是由 每个请求的平均输入和输出token总数 较大 以及 端到端总时延 较差导致的。
    - 每秒输出的token数 评估：良好（>1000），中等（<10-1000），较差（<10）。
    - 每秒输入和输出token总数 评估：良好（>1000），中等（<10-1000），较差（<10）。
    - 每个请求的平均输出token数 评估：精简（<1000），冗长（>1000）。
    - 失败请求数：如果存在失败的请求，请在“已识别问题”中指出。
    - 输出内容应控制在 300 字以内，技术性强，并优先处理最严重的问题。

    输出格式要求：
    ### 性能总结
    [1-3 句总体评估，包括用户体验判断和主要瓶颈。]

    ### 关键指标
    | 指标 | 值 | 结论 |
    |---|---|---|
    | 并发用户数 | N | — |
    | 压测时长 | X.XX | — |
    | 流式模式 | 流式/非流式 | — |
    | 数据集类型 | 纯文本/多模态 | — |
    | 首Token时延(s) | X.XX | 良好/中等/较差 |
    | 端到端总时延(s) | X.XX | 良好/中等/较差 |
    | 每秒处理的请求数 | X.XX | 良好/较低 |
    | 每秒输出的token数 | X.XX | 良好/中等/较差 |
    | 每秒输入和输出token总数| X.XX | 良好/中等/较差 |
    | 每个请求平均输出token数 | X.XX | 精简/冗长 |
    | 每个请求的平均输入和输出token总数 | X.XX | — |
    | 失败请求数 | N | — |

    ### 问题总结
    1. [具有指标值和影响的最关键问题（如果有）]
    2. [重点说明是否存在失败请求，并指引用户查看任务日志以获取具体的错误信息（如果有）]
    """

COMPARISON_PROMPT_EN = """
Analyze the performance results of multiple tasks, then generate a concise performance comparison analysis report.

Performance results: {model_info}

Rules:
- If a specific metric is not present in the provided {model_info}, skip its assessment and mark as N/A in the table.
- First_token_latency assessment: For text dataset: Good (<1s), Moderate (1–3s), Poor (>3s); For multimodal dataset: Good (<3s), Moderate (3–5s), Poor (>5s).
- Total_time assessment: Depends on the output length, the longer the output length, the longer the Total_time. Generally, if the average output token number per request is less than 1000, the Total_time is good (<30s), moderate (30–120s), poor (>120s); if the average output token number per request is greater than 1000, the Total_time is good (<120s), moderate (120–360s), poor (>360s).
- RPS assessment: Good (>10), Moderate (<10). If RPS is Moderate, please pay attention to whether the average input and output token number per request is large and the Total_time is poor.
- Completion_tps assessment: Good (>1000), Moderate (<10-1000), Poor (<10).
- Total_tps assessment: Good (>1000), Moderate (<10-1000), Poor (<10).
- Avg_completion_tokens/req assessment: Concise (>1000), Verbose (<1000).
- failure_request: If there is a failed request, please indicate it in the report.

Required Output Format:
### Performance Summary
[2–3 sentence overall assessment, keep it short and concise, including UX judgment and the dominant bottleneck(s).]

### Key Metrics
| Metric  | Task1 | Task2 | Conclusion |
|---|---|---|---|
| Concurrent_users |N | N | — |
| Duration |X.XX | X.XX | — |
| Stream_mode |streaming/non-streaming | streaming/non-streaming | — |
| Dataset_type |text/text-image | text/text-image | — |
| First_token_latency(s) |X.XX | X.XX | Good/Moderate/Poor |
| Total_time(s) |X.XX | X.XX | Good/Moderate/Poor |
| RPS |X.XX | X.XX | Good/Poor |
| Completion_tps |X.XX | X.XX | Good/Moderate/Poor |
| Total_tps|X.XX | X.XX | Good/Moderate/Poor |
| Avg_completion_tokens/req |X.XX | X.XX | Concise/Verbose |
| Avg_total_tokens/req |X.XX | X.XX | — |
| Failure_request|N | N | — |
[Add more columns as needed]

### Suggestions
1. [Based on the comparison, provide actionable suggestions]
2. [Configuration or model selection guidance]

Example:
Input:
({{
  "task_name": "migo-intern-0825",
  "model_name": "migo-intern",
  "concurrent_users": 100,
  "duration": "600s",
  "stream_mode": "streaming",
  "dataset_type": "text",
  "First_token_latency": 4.21,
  "Total_time": 64.94,
  "RPS": 0.46,
  "Completion_tps": 792.81,
  "Total_tps": 821.28,
  "Avg_completion_tokens/req": 1,958.35,
  "Avg_total_tokens/req": 2,028.67,
  "Failure_request": 0,
}}, {{
  "task_name": "puyu-intern-0825",
  "model_name": "puyu-intern",
  "concurrent_users": 100,
  "duration": "600s",
  "stream_mode": "streaming",
  "dataset_type": "text",
  "First_token_latency": 8.67,
  "Total_time": 10.50,
  "RPS": 2.44,
  "Completion_tps": 480.53,
  "Total_tps": 503.64,
  "Avg_completion_tokens/req": 1474.68,
  "Avg_total_tokens/req": 1545.60,
  "Failure_request": 0,
}})

Output:
### Performance Summary
Under the same test conditions (32 concurrent users, 600s, text conversation dataset, streaming output mode), migo-intern-0825 and puyu-intern-0825 show significantly different performance characteristics:
First Token Latency: migo-intern-0825 (4.21s) is better than puyu-intern-0825 (8.67s), indicating a certain advantage in response startup speed, but there is still a lot of room for improvement in user experience.
Token Throughput: migo-intern-0825's output token throughput and total token throughput are both higher than puyu-intern-0825, showing stronger streaming generation throughput.
End-to-End Response Time: migo-intern-0825's average is as high as 74.94s, far exceeding puyu-intern-0825's 10.50s, mainly driven by its extremely high average output length (1,958 tokens vs 1,475 tokens). This leads to excessive user waiting time and significantly degraded interactive experience.
System Throughput Bottleneck: both RPS are severely low (migo: 0.46 req/s, puyu: 2.44 req/s), indicating a service overall processing capacity bottleneck.
In summary, migo-intern-0825 has stronger streaming generation throughput, but due to its extremely long output length, the end-to-end delay is too high, and the system throughput is limited; while puyu-intern-0825 performs better in response speed and request throughput, suitable for high interactive scenarios.

### Metric Comparison
| Metric | migo-intern-0825 | puyu-intern-0825 | Conclusion |
|---|---|---|---|
| Model | migo-intern | puyu-intern | — |
| Concurrent Users | 32 | 32 | — |
| Duration | 600s | 600s | — |
| Stream Mode | streaming/non-streaming | streaming/non-streaming | — |
| Dataset Type | text/text-image | text/text-image | — |
| First Token Latency | 4.21s | 8.67s | all poor |
| Total Time | 64.94s | 10.50s | migo-intern-0825 poor, puyu-intern-0825 good |
| RPS | 0.46 req/s | 2.44 req/s | all poor |
| Completion TPS | 792.81 | 480.53 | all moderate |
| Total TPS | 821.28 | 503.64 | all moderate |
| Avg Completion Tokens/Req | 1,958.35 | 1474.68 | all verbose |
| Avg Total Tokens/Req | 2,028.67 | 1545.60 | — |
| Failure Request | 0 | 0 | no failure request |

### Suggestions
1. Optimize First Token Latency: Both models have First Token Latency over 4s, not ideal, suggest optimizing inference engine scheduling strategy, cache mechanism, etc.
2. Control Output Length: Both models have extremely long output lengths, suggest setting a reasonable max_new_tokens limit, or dynamically adjusting the output length according to the scene, to improve system throughput and user experience.
3. Balance Response Speed and Content Quality: According to the application scenario, choose the appropriate model. For high interactive scenarios, recommend using puyu-intern-0825, which has low end-to-end delay and high RPS, better user experience. For content generation-intensive or deep reasoning tasks, consider migo-intern-0825.
4. Analyze Throughput Bottleneck: Both models have low RPS, indicating a service overall processing capacity bottleneck, suggest analyzing the throughput bottleneck, optimizing the inference engine, model parameters, data preprocessing, etc.

"""
COMPARISON_PROMPT_CN = """
请分析以下多个任务的性能结果，然后生成一份简明的性能对比分析报告。

性能结果：{model_info}

指标评估规则：
- 如果提供的性能结果中不存在某个指标，请跳过该指标的评估，并在表格中标记为 N/A。
- 首Token时延 评估：对于纯文本数据集任务：良好（<1 秒），中等（1-3秒），较差（>3 秒）；对于多模态数据集任务：良好（<3 秒），中等（3-5 秒），较差（>5 秒）。
- 端到端总时延 评估：该指标取决于输出长度，输出长度越长，该指标越长。一般来说，如果每个请求的平均输出token数在1000以内，该指标良好（<30 秒），中等（30-120 秒），较差（>120 秒）；如果每个请求的平均输出token数在1000以上，该指标良好（<120 秒），中等（120-360 秒），较差（>360 秒）。
- 每秒处理的请求数 评估：良好（>10），一般（<10）。如果 每秒处理的请求数 为“一般”，请重点关注是不是由 每个请求的平均输入和输出token总数 较大 以及 端到端总时延 较差导致的。
- 每秒输出的token数 评估：良好（>1000），中等（<10-1000），较差（<10）。
- 每秒输入和输出token总数 评估：良好（>1000），中等（<10-1000），较差（<10）。
- 每个请求的平均输出token数 评估：精简（<1000），冗长（>1000）。
- 失败请求数：如果存在失败的请求，请在“已识别问题”中指出。

输出格式要求：
### 性能结论
[2-3 句总体评估，控制在 500 字以内，对比所有任务，突出整体性能最佳的任务/模型及关键指标，任务间的显著差异及具体数据，跨任务的共同问题或特定任务的问题]

### 详细指标对比
| 指标 |任务1 | 任务2| 结论 |
|---|---|---|---|
| 模型 | XX | XX | — |
| 并发用户数 | N | N | — |
| 压测时长 | X.XX | X.XX | — |
| 流式模式 | 流式/非流式 | 流式/非流式 | — |
| 数据集类型 | 纯文本/多模态 | 纯文本/多模态 | — |
| 首Token时延(s) | X.XX | X.XX | 良好/中等/较差 |
| 端到端总时延(s) | X.XX | X.XX | 良好/中等/较差 |
| 每秒处理的请求数 | X.XX | X.XX | 良好/较低 |
| 每秒输出的token数 | X.XX | X.XX | 良好/中等/较差 |
| 每秒输入和输出token总数| X.XX | X.XX | 良好/中等/较差 |
| 每个请求平均输出token数 | X.XX | X.XX | 精简/冗长 |
| 每个请求的平均输入和输出token总数 | X.XX | X.XX | — |
| 失败请求数 | N | N | — |
[根据需要添加更多列]

### 建议
1. [基于对比的可操作建议]
2. [配置或模型选择指导]


示例：
输入：
({{
  "task_name": "migo-intern-0825",
  "model_name": "migo-intern",
  "concurrent_users": 100,
  "duration": "600s",
  "stream_mode": "streaming",
  "dataset_type": "text",
}})
性能结果：(任务1：{{
  "First_token_latency": 4.21,
  "Total_time": 64.94,
  "RPS": 0.46,
  "Completion_tps": 792.81,
  "Total_tps": 821.28,
  "Avg_completion_tokens/req": 1,958.35,
  "Avg_total_tokens/req": 2,028.67,
  "Failure_request": 0,
}}, {{
  "task_name": "puyu-intern-0825",
  "model_name": "puyu-intern",
  "concurrent_users": 100,
  "duration": "600s",
  "stream_mode": "streaming",
  "dataset_type": "text",
  "First_token_latency": 8.67,
  "Total_time": 10.50,
  "RPS": 2.44,
  "Completion_tps": 480.53,
  "Total_tps": 503.64,
  "Avg_completion_tokens/req": 1474.68,
  "Avg_total_tokens/req": 1545.60,
  "Failure_request": 0,
}})

输出：
### 性能结论
在相同压测条件下（32并发、600秒、文本对话数据集，流式输出模式），migo-intern-0825 与 puyu-intern-0825 表现出显著不同的性能特征：
首Token时延方面：migo-intern-0825（4.21s）优于 puyu-intern-0825（8.67s），表明其在响应启动速度上具备一定优势，但用户体验仍有很大提升空间。
吞吐能力方面：migo-intern-0825 输出Token吞吐量和总Token吞吐量 均高于 puyu-intern-0825，显示出更强的流式生成吞吐能力。
端到端响应时延方面：migo-intern-0825 平均高达 74.94s，远超 puyu-intern-0825 的 10.50s，主要受其极高的平均输出长度影响（1,958 tokens vs 1,475 tokens）。这导致用户等待时间过长，交互体验明显劣化。
系统吞吐瓶颈方面：两者 RPS 均严重偏低（migo: 0.46 req/s, puyu: 2.44 req/s），反映出服务整体处理能力受限。
综上，migo-intern-0825 虽具备较强的流式生成吞吐能力，但因输出过长导致端到端延迟过高，系统吞吐受限；而 puyu-intern-0825 在响应速度和请求吞吐上表现更优，更适合高交互性场景。

### 详细指标对比
| 指标 |migo-intern-0825 | puyu-intern-0825 | 结论 |
|---|---|---|---|
| 模型 | migo-intern | puyu-intern | — |
| 并发用户数 | 32 | 32 | — |
| 压测时长 | 600s | 600s | — |
| 流式模式 | 流式 | 流式 | — |
| 数据集类型 | 纯文本 | 纯文本 | — |
| 首Token时延(s) | 4.21 | 8.67 | 均较差 |
| 端到端总时延(s) | 74.94 | 10.50 | migo-intern 中等，puyu-intern 良好 |
| 每秒处理的请求数 | 0.46 | 2.44 | 均较低 |
| 每秒输出的token数 | 792.81 | 480.53 | 均中等 |
| 每秒输入和输出token总数| 821.28 | 503.64 | 均中等 |
| 每个请求平均输出token数 | 1,958.35 | 1474.68 | 均冗长 |
| 每个请求的平均输入和输出token总数 | 2,028.67 | 1545.60 | — |
| 失败请求数 | 0 | 0 | 均无失败请求 |

### 建议
1.优化首Token时延：两模型首Token时延均超过4秒，未达理想水平，建议考虑优化推理引擎调度策略、缓存机制等；
2.控制输出长度：两模型的输出Token长度均冗长，建议设置合理的 max_new_tokens 上限，或者根据场景动态调整生成长度等，提升系统吞吐能力与用户体验；
3.平衡响应速度与内容质量：根据应用场景选择合适模型，对高交互性场景，推荐使用 puyu-intern-0825，其端到端延迟低、RPS 高，用户体验更佳，对内容生成密集型或者深度推理型任务，可考虑 migo-intern-0825。
4.分析吞吐瓶颈：两模型的 RPS 均较低，反映出服务整体处理能力受限，建议分析吞吐瓶颈，优化推理引擎、模型参数、数据预处理等。

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
