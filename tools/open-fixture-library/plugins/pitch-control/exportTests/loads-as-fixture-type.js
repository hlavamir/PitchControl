/**
 * @fileoverview
 * Checks an exported file against what PitchControl's fixture type model accepts and writes back unchanged
 * (`backend/src/pitchcontrol/config/models.py`: `FixtureType`, `ChannelMode`, `ChannelSlot`).
 * PitchControl's own test, `tools/ofl_plugin_check.py` in its repository, loads every file with the real model.
 */

/** @import { Fixture } from '../../../lib/model/Fixture.js' */

const TYPE_NAME_PATTERN = /^[A-Za-z0-9][\w .-]{0,63}$/;
const PIXEL_FORMATS = new Set(['I', 'RGB', 'RGBW']);
const SLOT_KINDS = ['value', 'pixels', 'macro', 'shutter'];
const MAX_DMX_VALUE = 255;

/**
 * @typedef {object} ExportFile
 * @property {string} name File name, may include slashes to provide a folder structure.
 * @property {string} content File content.
 * @property {string} mimetype File mime type.
 * @property {Fixture[] | null} fixtures Fixture objects that are described in given file; may be omitted if the file doesn't belong to any fixture (e.g. manufacturer information).
 * @property {string | null} mode Mode's shortName if given file only describes a single mode.
 */

/**
 * @param {unknown} value - Any value.
 * @returns {boolean} Whether it is a DMX value: an integer from 0 to 255.
 */
function isDmxValue(value) {
  return Number.isSafeInteger(value) && value >= 0 && value <= MAX_DMX_VALUE;
}

/**
 * @param {object} slot - A channel slot of a mode.
 * @param {string} where - Which slot this is, for the messages.
 * @returns {string[]} What is wrong with the slot.
 */
function checkSlot(slot, where) {
  const errors = [];
  const kinds = SLOT_KINDS.filter((kind) => slot[kind] !== undefined && slot[kind] !== null);
  if (kinds.length !== 1) {
    errors.push(`${where}: needs exactly one of ${SLOT_KINDS.join(', ')}, has ${kinds.length > 0 ? kinds.join(', ') : 'none'}`);
  }
  if ('name' in slot && typeof slot.name !== 'string') {
    errors.push(`${where}: name is not a string`);
  }
  if ('value' in slot && !isDmxValue(slot.value)) {
    errors.push(`${where}: value ${JSON.stringify(slot.value)} is not an integer from 0 to ${MAX_DMX_VALUE}`);
  }
  if ('pixels' in slot && !PIXEL_FORMATS.has(slot.pixels)) {
    errors.push(`${where}: pixels ${JSON.stringify(slot.pixels)} is not one of ${[...PIXEL_FORMATS].join(', ')}`);
  }
  if ('shutter' in slot && !(isDmxValue(slot.shutter?.open) && isDmxValue(slot.shutter?.strobo))) {
    errors.push(`${where}: shutter needs an open and a strobo value from 0 to ${MAX_DMX_VALUE}`);
  }
  return errors;
}

/**
 * @param {object} mode - A channel mode.
 * @param {number} index - Its position.
 * @returns {string[]} What is wrong with the mode.
 */
function checkMode(mode, index) {
  const where = `modes[${index}]`;
  const errors = [];
  for (const key of ['id', 'name']) {
    if (typeof mode[key] !== 'string' || mode[key] === '') {
      errors.push(`${where}: ${key} is missing`);
    }
  }
  if (typeof mode.description !== 'string') {
    errors.push(`${where}: description is not a string`);
  }
  if (!Number.isSafeInteger(mode.pixels) || mode.pixels < 1) {
    errors.push(`${where}: pixels is not an integer of at least 1`);
  }
  if (!Array.isArray(mode.channels) || mode.channels.length === 0) {
    errors.push(`${where}: channels is not a list with a channel`);
    return errors;
  }
  for (const [slotIndex, slot] of mode.channels.entries()) {
    errors.push(...checkSlot(slot, `${where}.channels[${slotIndex}]`));
  }
  return errors;
}

/**
 * @param {object} type - The parsed file.
 * @returns {string[]} What is wrong with the fixture type's own fields.
 */
function checkTypeFields(type) {
  const errors = [];
  if (typeof type.description !== 'string') {
    errors.push('description is not a string');
  }
  if (type.transport !== 'dmx') {
    errors.push(`transport is ${JSON.stringify(type.transport)}, not "dmx"`);
  }
  if (!(typeof type.gamma === 'number' && type.gamma > 0)) {
    errors.push('gamma is not a number above 0');
  }
  const color = type.strobo_color;
  if (['h', 's', 'b'].some((key) => !(typeof color?.[key] === 'number' && color[key] >= 0 && color[key] <= 1))) {
    errors.push('strobo_color needs h, s and b from 0 to 1');
  }
  if ('name' in type) {
    errors.push('name is the file name and must not be in the file');
  }
  return errors;
}

/**
 * @param {object[] | undefined} modes - The modes of the type.
 * @param {string} defaultMode - The `default_mode` of the type.
 * @returns {string[]} What is wrong with the modes.
 */
function checkModes(modes, defaultMode) {
  if (!Array.isArray(modes) || modes.length === 0) {
    return ['modes is not a list with a mode'];
  }
  const errors = modes.flatMap((mode, index) => checkMode(mode, index));
  const ids = modes.map((mode) => mode.id);
  if (new Set(ids).size !== ids.length) {
    errors.push(`mode ids are not unique: ${ids.join(', ')}`);
  }
  if (!ids.includes(defaultMode)) {
    errors.push(`default_mode '${defaultMode}' is not the id of a mode (${ids.join(', ')})`);
  }
  return errors;
}

/**
 * @param {ExportFile} exportFile - The file returned by the plugins' export module.
 * @param {ExportFile[]} allExportFiles - An array of all export files.
 * @returns {Promise<void, string[] | string>} Resolve when the test passes or reject with an array of errors or one error if the test fails.
 */
export default async function testLoadsAsFixtureType(exportFile, allExportFiles) {
  const typeName = exportFile.name.replace(/\.json$/, '');
  const errors = [];
  if (!exportFile.name.endsWith('.json') || !TYPE_NAME_PATTERN.test(typeName)) {
    errors.push(`the file name '${exportFile.name}' is not a type name PitchControl accepts (letters, digits, space, - _ . and at most 64, then .json)`);
  }

  let type;
  try {
    type = JSON.parse(exportFile.content);
  }
  catch (error) {
    throw new Error(`not JSON: ${error.message}`, { cause: error });
  }

  errors.push(...checkTypeFields(type), ...checkModes(type.modes, type.default_mode));

  if (errors.length > 0) {
    throw errors;
  }
}
