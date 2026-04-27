#!/usr/bin/env node
import { o as loadValidConfigOrThrow, d as resolveModelTarget } from '/usr/lib/node_modules/openclaw/dist/shared-CuNJ3-a_.js';
import { n as prepareSimpleCompletionModel, t as completeWithPreparedSimpleCompletionModel } from '/usr/lib/node_modules/openclaw/dist/simple-completion-runtime-ClkcCVid.js';

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', chunk => { data += chunk; });
    process.stdin.on('end', () => resolve(data));
    process.stdin.on('error', reject);
  });
}

function textFromCompletion(result) {
  const parts = Array.isArray(result?.content) ? result.content : [];
  return parts
    .filter(part => part && part.type === 'text' && typeof part.text === 'string')
    .map(part => part.text)
    .join('')
    .trim();
}

function stripCodeFence(text) {
  return text.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/i, '').trim();
}

function findBalancedJsonObject(text) {
  const start = text.indexOf('{');
  if (start < 0) return null;
  let depth = 0;
  let inString = false;
  let escape = false;
  for (let i = start; i < text.length; i++) {
    const ch = text[i];
    if (inString) {
      if (escape) escape = false;
      else if (ch === '\\') escape = true;
      else if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') {
      inString = true;
      continue;
    }
    if (ch === '{') depth++;
    else if (ch === '}') {
      depth--;
      if (depth === 0) return text.slice(start, i + 1);
    }
  }
  return null;
}

function parseJsonObject(text) {
  const cleaned = stripCodeFence(text.trim());
  try {
    const parsed = JSON.parse(cleaned);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed;
  } catch {}
  const balanced = findBalancedJsonObject(cleaned);
  if (!balanced) throw new Error('model response did not contain a JSON object');
  const parsed = JSON.parse(balanced);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('model response JSON was not an object');
  }
  return parsed;
}

async function main() {
  const input = JSON.parse(await readStdin());
  const prompt = String(input.prompt ?? '');
  const modelAlias = String(input.model ?? '').trim();
  if (!prompt) throw new Error('prompt is required');
  if (!modelAlias) throw new Error('model is required');

  const cfg = await loadValidConfigOrThrow();
  const ref = resolveModelTarget({ raw: modelAlias, cfg });
  const prepared = await prepareSimpleCompletionModel({
    cfg,
    provider: ref.provider,
    modelId: ref.model,
    agentDir: process.env.OPENCLAW_AGENT_DIR || '/root/.openclaw',
    allowMissingApiKeyModes: []
  });
  if (prepared.error) throw new Error(prepared.error);

  const options = {
    maxTokens: Number(input.maxTokens ?? 2048),
    temperature: Number(input.temperature ?? 0)
  };

  async function completeJson(userPrompt) {
    const completion = await completeWithPreparedSimpleCompletionModel({
      model: prepared.model,
      auth: prepared.auth,
      context: {
        messages: [{ role: 'user', content: userPrompt, timestamp: Date.now() }]
      },
      options
    });
    return textFromCompletion(completion);
  }

  let text = await completeJson(prompt);
  let parsed;
  try {
    parsed = parseJsonObject(text);
  } catch (firstErr) {
    const repairPrompt = `${prompt}\n\n你上一次输出不是合法 JSON。请重新输出，要求：只返回一个合法 JSON 对象；不要 markdown；不要解释；所有字符串必须正确转义；不要截断。`;
    text = await completeJson(repairPrompt);
    try {
      parsed = parseJsonObject(text);
    } catch (secondErr) {
      throw new Error(`failed to parse model JSON after retry: ${secondErr.message}; first error: ${firstErr.message}; response preview: ${text.slice(0, 500)}`);
    }
  }
  process.stdout.write(JSON.stringify(parsed));
}

main().catch(err => {
  process.stderr.write(`${err?.stack || err}\n`);
  process.exit(1);
});
