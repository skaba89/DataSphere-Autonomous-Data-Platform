/**
 * DataSphere API load test — k6
 *
 * Usage:
 *   k6 run load_tests/k6_script.js
 *   k6 run --vus 50 --duration 60s load_tests/k6_script.js
 *   BASE_URL=http://localhost:8000 k6 run load_tests/k6_script.js
 */
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

// Custom metrics
const errorRate = new Rate('errors');
const generateDuration = new Trend('generate_duration');

export const options = {
  stages: [
    { duration: '10s', target: 10 },   // ramp up
    { duration: '30s', target: 50 },   // steady state
    { duration: '10s', target: 100 },  // stress
    { duration: '10s', target: 0 },    // ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'],   // 95% of requests < 2s
    http_req_failed: ['rate<0.05'],      // error rate < 5%
    errors: ['rate<0.1'],
  },
};

const BUSINESS_REQUESTS = [
  'Pipeline analytics ventes',
  'Dashboard KPIs marketing',
  'Plateforme données RH',
];

const CLOUDS = ['aws', 'gcp', 'azure'];
const WAREHOUSES = ['snowflake', 'bigquery', 'postgresql'];

function randomItem(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

export default function () {
  const headers = { 'Content-Type': 'application/json' };

  // Health check
  let res = http.get(`${BASE_URL}/healthz`);
  check(res, { 'healthz 200': (r) => r.status === 200 });
  errorRate.add(res.status !== 200);

  sleep(0.5);

  // Generate dbt project
  const start = Date.now();
  res = http.post(`${BASE_URL}/dbt/generate`, JSON.stringify({
    business_request: randomItem(BUSINESS_REQUESTS),
    data_warehouse: randomItem(WAREHOUSES),
    ingestion: 'airbyte',
  }), { headers });
  generateDuration.add(Date.now() - start);
  check(res, { 'dbt/generate 200': (r) => r.status === 200 });
  errorRate.add(res.status !== 200);

  sleep(0.5);

  // Cost estimate
  res = http.post(`${BASE_URL}/costs/estimate`, JSON.stringify({
    stack: {
      cloud_provider: randomItem(CLOUDS),
      data_warehouse: randomItem(WAREHOUSES),
      orchestrator: 'airflow',
      ingestion: 'airbyte',
      transformation: 'dbt',
      bi_tool: 'metabase',
    },
    budget: 'medium',
  }), { headers });
  check(res, { 'costs/estimate 200': (r) => r.status === 200 });

  sleep(0.5);

  // Get templates
  res = http.get(`${BASE_URL}/templates`);
  check(res, {
    'templates 200': (r) => r.status === 200,
    'templates has data': (r) => JSON.parse(r.body).count > 0,
  });

  sleep(randomItem([0.5, 1.0, 1.5]));
}

export function handleSummary(data) {
  return {
    'load_tests/results/k6_summary.json': JSON.stringify(data, null, 2),
    stdout: `
=== DataSphere Load Test Summary ===
Total requests: ${data.metrics.http_reqs.values.count}
Error rate: ${(data.metrics.http_req_failed.values.rate * 100).toFixed(2)}%
Avg response time: ${data.metrics.http_req_duration.values.avg.toFixed(0)}ms
p95 response time: ${data.metrics.http_req_duration.values['p(95)'].toFixed(0)}ms
`,
  };
}
