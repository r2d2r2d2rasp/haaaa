/** Decodifica un punto EWKB esadecimale (come lo restituisce PostgREST per geography) → {lat, lon}. */
export function parsePoint(hex: string | null | undefined): { lat: number; lon: number } | null {
  if (!hex || hex.length < 50) return null;
  const buf = Buffer.from(hex, "hex");
  const le = buf[0] === 1;
  const type = le ? buf.readUInt32LE(1) : buf.readUInt32BE(1);
  const hasSrid = (type & 0x20000000) !== 0;
  const off = 5 + (hasSrid ? 4 : 0);
  return le
    ? { lon: buf.readDoubleLE(off), lat: buf.readDoubleLE(off + 8) }
    : { lon: buf.readDoubleBE(off), lat: buf.readDoubleBE(off + 8) };
}

export function haversine(a: [number, number], b: [number, number]): number {
  const R = 6371000, rad = Math.PI / 180;
  const dLat = (b[1] - a[1]) * rad, dLon = (b[0] - a[0]) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * rad) * Math.cos(b[1] * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
