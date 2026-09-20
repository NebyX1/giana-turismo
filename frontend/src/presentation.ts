const citationMarker = /\[\s*\d+(?:\s*[,;]\s*\d+)*\s*\]/g;

export function stripCitationMarkers(text: string): string {
  return String(text || '')
    .replace(citationMarker, '')
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/[ \t]+([,.;:])/g, '$1')
    .trim();
}
