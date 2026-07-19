/**
 * Pipeline stage / inspiration message helpers.
 *
 * Keys live in client/lib/i18n/t-pipeline.js (20 locales). Callers pass the
 * language `t` function from useLanguage() so this module stays free of React.
 */

export const STAGE_MESSAGE_KEYS = {
  screenwriting: [
    "pipeline_screenwriting_1",
    "pipeline_screenwriting_2",
    "pipeline_screenwriting_3",
    "pipeline_screenwriting_4",
  ],
  portraits: [
    "pipeline_portraits_1",
    "pipeline_portraits_2",
    "pipeline_portraits_3",
  ],
  storyboard: [
    "pipeline_storyboard_1",
    "pipeline_storyboard_2",
    "pipeline_storyboard_3",
  ],
  frames: [
    "pipeline_frames_1",
    "pipeline_frames_2",
    "pipeline_frames_3",
    "pipeline_frames_4",
  ],
  video: [
    "pipeline_video_1",
    "pipeline_video_2",
    "pipeline_video_3",
    "pipeline_video_4",
  ],
  assembly: [
    "pipeline_assembly_1",
    "pipeline_assembly_2",
    "pipeline_assembly_3",
  ],
  music: [
    "pipeline_music_1",
    "pipeline_music_2",
    "pipeline_music_3",
  ],
  complete: [
    "pipeline_complete_1",
    "pipeline_complete_2",
  ],
  error: [
    "pipeline_error_1",
    "pipeline_error_2",
  ],
};

export const INSPIRATION_KEYS = [
  "pipeline_inspo_1",
  "pipeline_inspo_2",
  "pipeline_inspo_3",
  "pipeline_inspo_4",
  "pipeline_inspo_5",
  "pipeline_inspo_6",
];

/**
 * @param {string} stage
 * @param {number} [idx]
 * @param {(key: string) => string} t  language lookup from useLanguage()
 */
export function getStageMessage(stage, idx = 0, t) {
  const keys = STAGE_MESSAGE_KEYS[stage];
  if (!keys || typeof t !== "function") return "";
  return t(keys[idx % keys.length]);
}

/**
 * @param {number} [seed]
 * @param {(key: string) => string} t  language lookup from useLanguage()
 */
export function getInspirationMessage(seed = 0, t) {
  if (typeof t !== "function") return "";
  return t(INSPIRATION_KEYS[seed % INSPIRATION_KEYS.length]);
}
