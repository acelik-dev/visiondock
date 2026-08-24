/** Client-side sample files for non-technical dataset upload. */

function downloadBlob(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function downloadMultiLabelTemplate(labels: string[] = ["scratch", "rust", "clean"]) {
  const tagA = labels[0] ?? "scratch";
  const tagB = labels[1] ?? "rust";
  const tagC = labels[2] ?? "clean";
  const csv = [
    "image,labels",
    `part1.jpg,"${tagA}, ${tagB}"`,
    `part2.jpg,${tagC}`,
    `part3.jpg,"${tagA}"`,
  ].join("\n");
  downloadBlob("visiondock-label-list-example.csv", csv, "text/csv;charset=utf-8");
}

export function downloadRegressionTemplate(targetName = "target") {
  const col = targetName.trim() || "target";
  const csv = ["image," + col, "part1.jpg,12.5", "part2.jpg,18.0", "part3.jpg,9.2"].join("\n");
  downloadBlob("visiondock-measurement-list-example.csv", csv, "text/csv;charset=utf-8");
}

/** Tiny 1×1 PNG as base64 — used only inside the sample ZIP helper text package. */
const TINY_PNG_B64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

/**
 * Download a minimal YOLO-style sample ZIP (data.yaml + 1 image + 1 label).
 * Built without extra deps using a hand-rolled store-only ZIP.
 */
export function downloadDetectionSampleZip() {
  const png = Uint8Array.from(atob(TINY_PNG_B64), (c) => c.charCodeAt(0));
  const dataYaml = [
    "path: .",
    "train: images",
    "val: images",
    "names:",
    "  0: defect",
    "",
  ].join("\n");
  const labelTxt = "0 0.5 0.5 0.4 0.4\n";
  const readme = [
    "VisionDock sample labeled package",
    "",
    "This is a tiny example so you can see the folder layout.",
    "Replace images/ and labels/ with your own photos and boxes.",
    "You can export this layout from Roboflow, Label Studio, or CVAT (YOLO format).",
    "",
  ].join("\n");

  const files: { name: string; data: Uint8Array }[] = [
    { name: "data.yaml", data: new TextEncoder().encode(dataYaml) },
    { name: "README.txt", data: new TextEncoder().encode(readme) },
    { name: "images/sample.jpg", data: png },
    { name: "labels/sample.txt", data: new TextEncoder().encode(labelTxt) },
  ];

  const blob = buildStoreZip(files);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "visiondock-labeled-package-example.zip";
  a.click();
  URL.revokeObjectURL(url);
}

function crc32(buf: Uint8Array): number {
  let c = ~0;
  for (let i = 0; i < buf.length; i++) {
    c ^= buf[i];
    for (let k = 0; k < 8; k++) {
      c = (c >>> 1) ^ (0xedb88320 & -(c & 1));
    }
  }
  return ~c >>> 0;
}

function u16(n: number): Uint8Array {
  const b = new Uint8Array(2);
  new DataView(b.buffer).setUint16(0, n, true);
  return b;
}

function u32(n: number): Uint8Array {
  const b = new Uint8Array(4);
  new DataView(b.buffer).setUint32(0, n, true);
  return b;
}

function concat(parts: Uint8Array[]): Uint8Array {
  const len = parts.reduce((s, p) => s + p.length, 0);
  const out = new Uint8Array(len);
  let o = 0;
  for (const p of parts) {
    out.set(p, o);
    o += p.length;
  }
  return out;
}

function buildStoreZip(files: { name: string; data: Uint8Array }[]): Blob {
  const localParts: Uint8Array[] = [];
  const centralParts: Uint8Array[] = [];
  let offset = 0;

  for (const file of files) {
    const nameBytes = new TextEncoder().encode(file.name);
    const crc = crc32(file.data);
    const local = concat([
      u32(0x04034b50),
      u16(20),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(crc),
      u32(file.data.length),
      u32(file.data.length),
      u16(nameBytes.length),
      u16(0),
      nameBytes,
      file.data,
    ]);
    const central = concat([
      u32(0x02014b50),
      u16(20),
      u16(20),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(crc),
      u32(file.data.length),
      u32(file.data.length),
      u16(nameBytes.length),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(0),
      u32(offset),
      nameBytes,
    ]);
    localParts.push(local);
    centralParts.push(central);
    offset += local.length;
  }

  const centralDir = concat(centralParts);
  const end = concat([
    u32(0x06054b50),
    u16(0),
    u16(0),
    u16(files.length),
    u16(files.length),
    u32(centralDir.length),
    u32(offset),
    u16(0),
  ]);

  const bytes = concat([...localParts, centralDir, end]);
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  return new Blob([copy], { type: "application/zip" });
}

/** Map backend validation messages to plain language. */
export function friendlyValidationMessage(raw: string): string {
  const s = raw.trim();
  const lower = s.toLowerCase();
  if (lower.includes("not validated") || lower.includes("is not validated")) {
    return "Not ready yet — finish the steps below.";
  }
  if (lower.includes("unknown class") || lower.includes("unknown label")) {
    return s.replace(/unknown class/i, "This group is not part of your task").replace(/'/g, "");
  }
  if (lower.includes("manifest references") || lower.includes("missing from manifest") || lower.includes("unlabeled")) {
    return "Some photo names in the list don’t match uploaded file names yet. Check spelling or re-upload.";
  }
  if (lower.includes("missing targets") || lower.includes("reference images not uploaded")) {
    return "Some photo names in the measurement list don’t match uploaded photos yet.";
  }
  if (lower.includes("expected classes not found")) {
    return "Your package labels don’t include every object type from the task yet.";
  }
  if (lower.includes("expected labels not in manifest")) {
    return "Your label list doesn’t include every tag from the task yet.";
  }
  if (lower.includes("manifest")) {
    return "Add the label list that matches your photos.";
  }
  if (lower.includes("targets") || lower.includes("target csv")) {
    return "Add the measurement list (one number per photo).";
  }
  if (lower.includes("need at least") && lower.includes("class")) {
    return "Add more photos to each group (minimum not met yet).";
  }
  if (lower.includes("no images") || lower.includes("no image")) {
    return "Add some photos first.";
  }
  if (lower.includes("data.yaml") || lower.includes("yolo") || lower.includes("coco") || lower.includes("voc")) {
    return "This package is missing labels or folder layout. Download the sample package to see how it should look.";
  }
  if (lower.includes("zip")) {
    return "Upload one ZIP file that contains your labeled photos.";
  }
  return s;
}
