import { fixtureSchema } from '../../lib/esm-shim.cjs';
import { shortReason } from './convert.js';
import { buildTypeFile, oflJsonOf } from './type-file.js';
/** @import Fixture from '../../lib/model/Fixture.js' */

export const version = '1.0.0';

/** What PitchControl accepts as a type name: at most 64 characters, so a number added to a name that is taken must fit. */
const MAX_NAME_LENGTH = 64;

/**
 * Every fixture becomes one PitchControl fixture type file, `<type name>.json`, with the same content that
 * PitchControl's own File → Import Fixture → Open Fixture Library makes from the fixture's JSON.
 * A fixture none of whose modes PitchControl can express (see README.md) gets no file; if that is every fixture
 * asked for, the export fails with the reason.
 * @param {Fixture[]} fixtures - An array of Fixture objects.
 * @param {object} options - Global options, including:
 * @param {string} options.baseDirectory - Absolute path to OFL's root directory.
 * @param {Date} options.date - The current time.
 * @param {string | undefined} options.displayedPluginVersion - Replacement for plugin version if the plugin version is used in export.
 * @returns {Promise<object[], Error>} The generated files.
 */
export async function exportFixtures(fixtures, options) {
  const files = [];
  const usedNames = new Set();
  const unsupported = [];

  for (const fixture of fixtures) {
    const key = `${fixture.manufacturer.key}/${fixture.key}`;

    let typeFile;
    try {
      typeFile = buildTypeFile(oflJsonOf(fixture.jsonObject), {
        key,
        manufacturer: fixture.manufacturer.name || undefined,
        schemaVersion: fixtureSchema.version,
      });
    }
    catch (error) {
      throw new Error(`Exporting fixture ${key} failed: ${error}`, {
        cause: error,
      });
    }

    if (typeFile.content === undefined) {
      const reasons = [...new Set(typeFile.skipped.map(([, why]) => shortReason(why)))];
      unsupported.push(`${key} (${reasons.join('; ')})`);
      continue;
    }

    files.push({
      name: `${uniqueName(typeFile.name, usedNames)}.json`,
      content: `${JSON.stringify(typeFile.content, null, 2)}\n`,
      mimetype: 'application/json',
      fixtures: [fixture],
    });
  }

  if (files.length === 0) {
    throw new Error(`PitchControl can't express any mode of ${unsupported.join(', ')}.`);
  }

  return files;
}

/**
 * Two fixtures can give the same type name ("LED Bar 240/8" and "LED Bar 240-8"), and PitchControl ignores the
 * letter case of a name.
 * @param {string} name - The type name.
 * @param {Set<string>} usedNames - The lower-case names used so far; the one returned is added.
 * @returns {string} The name, or the name with `-2`, `-3` … when it is taken.
 */
function uniqueName(name, usedNames) {
  let candidate = name;
  let number = 2;
  while (usedNames.has(candidate.toLowerCase())) {
    const suffix = `-${number}`;
    candidate = `${name.slice(0, MAX_NAME_LENGTH - suffix.length).trimEnd()}${suffix}`;
    number += 1;
  }
  usedNames.add(candidate.toLowerCase());
  return candidate;
}
