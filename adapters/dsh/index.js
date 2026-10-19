import z from '@deepseek-ai/schemastery';
import { install } from './bridge.js';
import { EMPTY_PROFILES, parseProfiles } from './profiles.js';

export const name = 'completionqa';
// completionQAHost is this package's required trusted integration seam, not a
// built-in DSH service. Missing integration must block activation.
export const inject = ['agentTeams', 'tools', 'completionQAHost'];
export const Config = z.object({
  profilesJson: z.transform(z.string(), value => { parseProfiles(value); return value; })
    .default(EMPTY_PROFILES).description('Named profiles JSON: roles, models, effort and fallbacks. Native model selection is blocked.').volatile(),
  inheritModel: z.boolean().default(false).volatile(),
  maxConcurrent: z.number().step(1).min(1).default(1).volatile(),
});
export function apply(ctx, config) { return install(ctx, config); }
