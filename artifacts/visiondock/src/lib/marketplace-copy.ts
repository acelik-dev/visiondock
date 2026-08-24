import type { TaskType } from "@/lib/project-spec";
import { TASK_LABELS } from "@/lib/project-spec";

export type MarketplaceItemCopy = {
  headline: string;
  whatItIs: string;
  goodFor: string;
  startProjectHint: string;
  detailBlurb?: string;
  classHint?: string;
};

export const DATASET_LIBRARY_INTRO = {
  title: "Ready-made training photo sets",
  body: "Each dataset is a collection of example images already organized for a specific kind of vision task. You do not need to collect or label photos yourself — pick one and VisionDock creates a new project with the data loaded and ready for training.",
  startNote:
    "Start project opens a brand-new workspace with this dataset. It does not add to your current project.",
};

export const MODEL_LIBRARY_INTRO = {
  title: "Ready-to-train model architectures",
  body: "Each card is a proven model design (EfficientNet, YOLOv8, etc.) with recommended settings for a vision task. Start project creates a new workspace pre-configured for that architecture — you define your own labels and upload your photos.",
  startNote:
    "Catalog category names (Imagenette, VOC, …) are reference only. Start project locks the architecture and task type — not those demo labels. You name your groups and train on your data.",
};

export const TASK_TYPE_PLAIN: Record<TaskType, { title: string; explanation: string; example: string }> = {
  classification: {
    title: "Single choice per image",
    explanation: "The AI learns to assign exactly one category to each photo.",
    example: "Example: Is this product OK or defective?",
  },
  multi_label: {
    title: "Multiple tags per image",
    explanation: "One photo can have several labels at the same time.",
    example: "Example: A street scene tagged with car, person, and traffic light.",
  },
  regression: {
    title: "A number per image",
    explanation: "The AI predicts a continuous value instead of a category.",
    example: "Example: Estimate someone’s age or a product’s weight from a photo.",
  },
  object_localization: {
    title: "Find one main object",
    explanation: "The AI draws a box around the most important object in the image.",
    example: "Example: Locate the single product on a conveyor belt.",
  },
  object_detection: {
    title: "Find many objects",
    explanation: "The AI finds and boxes every instance of objects it knows.",
    example: "Example: Count people and vehicles in a security camera frame.",
  },
};

export const DATASET_COPY: Record<string, MarketplaceItemCopy> = {
  "imagenette-160": {
    headline: "Everyday object photos in 10 categories",
    whatItIs:
      "A teaching set of real-world photos (animals, devices, vehicles) used to practice image sorting. Each image belongs to exactly one category.",
    goodFor: "Learning how classification works, demos, and quick prototypes.",
    startProjectHint: "You’ll get a new project with photos sorted into 10 folders — ready to train.",
    detailBlurb: "Photos are grouped into folders — one folder per category. The model learns to pick the right folder for a new image.",
    classHint: "All 10 categories are listed below — each photo has exactly one label.",
  },
  "cifar-10": {
    headline: "Small photos of common objects",
    whatItIs:
      "Thousands of tiny images across 10 everyday classes (cars, animals, vehicles). A classic starter set for image recognition.",
    goodFor: "Fast experiments and understanding classification at scale.",
    startProjectHint: "You’ll get a new project with all classes pre-loaded.",
    detailBlurb: "Classic 32×32 color images — great for quick training runs.",
    classHint: "Ten everyday object types:",
  },
  "voc-2012-detection": {
    headline: "Street & indoor scenes with object boxes",
    whatItIs:
      "Photos where objects (people, cars, furniture, etc.) are already marked with rectangles. The AI learns to find multiple objects per image.",
    goodFor: "Safety monitoring, retail shelf checks, and multi-object counting.",
    startProjectHint: "You’ll get a new detection project with annotated images in a ZIP.",
    detailBlurb: "Each image may contain several objects. Boxes show where each object is and which type it is.",
    classHint: "20 object types from the PASCAL VOC benchmark — all listed below.",
  },
  "voc-single-object": {
    headline: "One highlighted object per photo",
    whatItIs:
      "Similar to the detection set, but each image focuses on locating a single main object — good when only one item matters.",
    goodFor: "Product picking, quality inspection of one item per frame.",
    startProjectHint: "You’ll get a new localization project with pre-drawn boxes.",
    detailBlurb: "Each frame highlights one primary object with a bounding box.",
    classHint: "Locates one of these object types per image:",
  },
  "voc-multilabel": {
    headline: "Photos with several labels each",
    whatItIs:
      "Images paired with a list of what appears in them (not just one tag). Teaches the AI to handle multiple attributes per photo.",
    goodFor: "Scene tagging, content moderation, and attribute search.",
    startProjectHint: "You’ll get images plus a spreadsheet mapping each file to its labels.",
    detailBlurb: "Scene photos tagged with every object or attribute that appears.",
    classHint: "Each image can have multiple of these tags:",
  },
  "utkface-age": {
    headline: "Face photos with age numbers",
    whatItIs:
      "Portrait images where the training target is a person’s age in years — a regression task (predict a number, not a category).",
    goodFor: "Age estimation demos and numeric prediction from images.",
    startProjectHint: "You’ll get photos and a CSV file linking each image to an age value.",
    detailBlurb: "Portrait photos paired with age in years — no categories, just a number.",
    classHint: "Predicts age (years), not a category label.",
  },
};

export const MODEL_COPY: Record<string, MarketplaceItemCopy> = {
  "efficientnet-imagenette": {
    headline: "EfficientNet for single-label image sorting",
    whatItIs:
      "A lightweight classifier architecture suited to everyday object categories. Benchmark numbers come from training on Imagenette — you will train the same architecture on your own folders.",
    goodFor: "Product sorting, quality buckets, and any one-label-per-photo task.",
    startProjectHint: "Opens a classification project — add your own group names, upload photos, then train.",
    detailBlurb: "EfficientNet-B0 backbone — accurate and fast on GPU.",
    classHint: "Reference demo categories (you replace these):",
  },
  "efficientnet-cifar10": {
    headline: "EfficientNet for small, simple photos",
    whatItIs:
      "The same EfficientNet family tuned for low-resolution inputs. Reference scores are from CIFAR-10 — you bring your own classes and images.",
    goodFor: "Quick experiments when photos are small or thumbnails.",
    startProjectHint: "Starts a classification workspace — name your groups, then add photos before training.",
    detailBlurb: "Compact EfficientNet for small inputs.",
    classHint: "Reference demo object types (optional):",
  },
  "yolov8n-voc-detection": {
    headline: "YOLOv8 nano for multi-object detection",
    whatItIs:
      "A fast detector that finds and boxes every instance in a scene. Reference mAP is from PASCAL VOC — you train on your own annotated ZIP.",
    goodFor: "Safety monitoring, shelf checks, and counting multiple items.",
    startProjectHint: "Opens a detection project — upload a YOLO/COCO-style ZIP with your classes in Step 2.",
    detailBlurb: "YOLOv8n — optimized for speed on T4 GPUs.",
    classHint: "Reference demo classes (your ZIP defines the real ones):",
  },
  "yolov8n-voc-localization": {
    headline: "YOLOv8 nano for single-object localization",
    whatItIs:
      "Finds one primary object per image with a bounding box. Train it on your own single-target scenes.",
    goodFor: "Pick-and-place, one product per frame, focused inspection.",
    startProjectHint: "Starts localization training — provide your boxed dataset in Step 2.",
    detailBlurb: "Single-box YOLO head for one main subject per image.",
    classHint: "Reference demo object types:",
  },
  "efficientnet-voc-multilabel": {
    headline: "EfficientNet for multi-tag images",
    whatItIs:
      "Predicts several labels per photo instead of one winner. You define the tag set and upload matching training data.",
    goodFor: "Catalog tags, scene attributes, and search facets.",
    startProjectHint: "Multi-label project — upload images plus a label list with your tags in Step 2.",
    detailBlurb: "Shared backbone with sigmoid outputs per tag.",
    classHint: "Reference demo tags (your CSV defines the real ones):",
  },
  "efficientnet-age-regression": {
    headline: "EfficientNet for numeric prediction from faces",
    whatItIs:
      "Outputs a continuous value (e.g. age) per image. Reference scores used UTKFace — you supply photos and target numbers.",
    goodFor: "Any regression task with one number per image.",
    startProjectHint: "Regression project — upload images and a CSV of your target values in Step 2.",
    detailBlurb: "EfficientNet regressor head for scalar targets.",
    classHint: "No fixed categories — you define the numeric target column.",
  },
};

export function getDatasetCopy(id: string, name: string): MarketplaceItemCopy {
  return (
    DATASET_COPY[id] ?? {
      headline: name,
      whatItIs: "A curated public dataset packaged for VisionDock training.",
      goodFor: "Exploring this type of vision task with real examples.",
      startProjectHint: "Starts a new project with this data loaded.",
    }
  );
}

export function getModelCopy(id: string, name: string): MarketplaceItemCopy {
  return (
    MODEL_COPY[id] ?? {
      headline: name,
      whatItIs: "A proven model architecture packaged for VisionDock training.",
      goodFor: "Starting quickly with the right backbone for your task.",
      startProjectHint: "Opens a training project — upload your labeled data in Step 2.",
    }
  );
}

export function humanMetricLabel(key: string): string {
  const map: Record<string, string> = {
    accuracy: "Accuracy",
    val_accuracy: "Validation accuracy",
    micro_f1: "Overall match score",
    macro_f1: "Average per-tag score",
    f1: "Match score",
    mAP50: "Detection quality",
    "mAP50-95": "Detection quality (strict)",
    mae: "Average error",
    rmse: "Typical error",
    r2: "Fit quality",
  };
  return map[key] ?? key.replace(/_/g, " ");
}

export function humanArchitecture(name: string): string {
  if (name.startsWith("yolov8")) return "Object finder (YOLO)";
  if (name.includes("efficientnet")) return "Image classifier (EfficientNet)";
  return name;
}

const MODEL_DISPLAY_TITLES: Record<string, string> = {
  "efficientnet-imagenette": "EfficientNet · Image classification",
  "efficientnet-cifar10": "EfficientNet · Small-image classification",
  "efficientnet-voc-multilabel": "EfficientNet · Multi-label tags",
  "efficientnet-age-regression": "EfficientNet · Numeric regression",
  "yolov8n-voc-detection": "YOLOv8n · Multi-object detection",
  "yolov8n-voc-localization": "YOLOv8n · Single-object localization",
};

/** Unique card title — architecture + task, no benchmark dataset names. */
export function displayModelTitle(model: {
  id: string;
  name: string;
  architecture?: string;
  task_type?: TaskType;
}): string {
  if (MODEL_DISPLAY_TITLES[model.id]) return MODEL_DISPLAY_TITLES[model.id];
  const copy = MODEL_COPY[model.id];
  if (copy?.headline) return copy.headline;
  const arch = model.architecture?.trim();
  if (arch && model.task_type) {
    return `${arch.replace(/_/g, "-")} · ${TASK_LABELS[model.task_type as TaskType] ?? model.task_type}`;
  }
  if (arch) return arch.replace(/_/g, "-");
  return model.name.split("·")[0]?.trim() || model.name;
}
