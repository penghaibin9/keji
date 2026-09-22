# PDF 13.7 / 13.8 学校环境性能验收

本工具只在学校或等效预发布环境运行，不在生产高峰期执行。

## 测什么

1. 20 个真实账号并发登录，默认登录 P95 ≤ 3 秒；
2. 3000 个唯一测试账号建立在线会话，并抽样验证会话仍有效；
3. 100 个已登录用户同时访问培训台账、待办、考核列表和统计驾驶舱；
4. 普通业务接口 P95 ≤ 3 秒，统计接口 P95 ≤ 5 秒，验收流量 HTTP 错误数为 0；
5. 仅 HTTPS 且证书正常校验的结果可作为正式环境证据。

## 凭据 CSV

UTF-8 CSV，仅两列：`username,password`。正式验收建议 3000 个独立性能测试账号。Linux 上文件必须 `chmod 600`。工具不会把密码、Cookie、CSRF 写进结果。

```csv
username,password
perf0001,临时强密码
perf0002,临时强密码
```

## 执行

```bash
chmod 600 /secure/perf-users.csv
bash scripts/run_performance_acceptance.sh \
  https://nondegree.school.example \
  /secure/perf-users.csv \
  /var/log/nondegree/performance-acceptance.json
```

若学校预发布环境不足 3000 个测试账号，可以先用 `--online-target 100` 做施工预检，但这种结果不能替代采购条款中的 3000 在线验收。

## 判读

- `overall_pass=true` 才表示本次完整性能门通过；
- `BLOCKED_INPUT` 表示测试账号不足，不是系统性能失败；
- 每个端点分别输出请求数、错误率、P50/P95/P99/最大耗时和 HTTP 状态统计；
- 结果只适用于本次服务器、MySQL、网络、数据规模和负载模型。
