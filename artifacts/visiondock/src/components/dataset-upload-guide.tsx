import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import {
  downloadDetectionSampleZip,
  downloadMultiLabelTemplate,
  downloadRegressionTemplate,
} from "@/lib/dataset-templates";
import type { TaskType } from "@/lib/project-spec";
import { navigateToView } from "@/lib/navigation";
import { CheckCircle2, Circle, Download, Library, Sparkles } from "lucide-react";

export type UploadChecklistItem = {
  id: string;
  label: string;
  done: boolean;
};

type Props = {
  taskType: TaskType;
  checklist: UploadChecklistItem[];
  targetName?: string;
  labels?: string[];
  marketplaceLinked?: boolean;
  marketplaceLabel?: string;
  minImagesPerClass?: number;
};

export function DatasetUploadGuide({
  taskType,
  checklist,
  targetName = "target",
  labels = [],
  marketplaceLinked = false,
  marketplaceLabel,
  minImagesPerClass = 5,
}: Props) {
  const allDone = checklist.length > 0 && checklist.every((c) => c.done);

  return (
    <div className="space-y-4">
      {!marketplaceLinked && (
        <button
          type="button"
          onClick={() => navigateToView("datasets")}
          className="w-full text-left rounded-xl border border-emerald-200 bg-emerald-50/80 px-5 py-4 hover:bg-emerald-50 transition-colors"
        >
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-card border border-emerald-200">
              <Library className="h-5 w-5 text-emerald-700" />
            </div>
            <div>
              <p className="text-sm font-semibold text-emerald-950">Easiest: use a ready dataset</p>
              <p className="text-xs text-emerald-800 mt-0.5">
                Open the Dataset Library and pick a prepared set — no file packing needed.
              </p>
            </div>
          </div>
        </button>
      )}

      {marketplaceLinked && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-5 py-4">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5 text-emerald-600" />
            <p className="text-sm font-semibold text-emerald-900">
              {marketplaceLabel ?? "Library dataset"} is linked — ready for training
            </p>
          </div>
        </div>
      )}

      {taskType === "classification" && (
        <div className="vd-panel px-5 py-4">
          <p className="text-xs font-semibold text-foreground/80 mb-2">How it should look</p>
          <p className="text-xs text-muted-foreground mb-3">
            Each group below gets its own photos. Add at least {minImagesPerClass} photos per group.
          </p>
          <div className="flex flex-wrap gap-3">
            {["Group A", "Group B"].map((name) => (
              <div
                key={name}
                className="flex items-center gap-2 rounded-lg border border-dashed border-border bg-muted/40 px-3 py-2"
              >
                <div className="flex -space-x-1">
                  {[0, 1, 2].map((i) => (
                    <div
                      key={i}
                      className="h-7 w-7 rounded border border-white bg-muted shadow-sm"
                      style={{ opacity: 1 - i * 0.15 }}
                    />
                  ))}
                </div>
                <span className="text-xs font-medium text-foreground/80">{name}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {taskType === "multi_label" && (
        <div className="vd-panel px-5 py-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-xs font-semibold text-foreground/80">Example label list</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                Each row: photo name, then tags separated by commas.
              </p>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8 text-xs"
              onClick={() => downloadMultiLabelTemplate(labels)}
            >
              <Download className="h-3.5 w-3.5 mr-1.5" />
              Download example CSV
            </Button>
          </div>
          <ExampleTable
            headers={["Photo", "Tags"]}
            rows={[
              ["part1.jpg", "scratch, rust"],
              ["part2.jpg", "clean"],
            ]}
          />
        </div>
      )}

      {taskType === "regression" && (
        <div className="vd-panel px-5 py-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-xs font-semibold text-foreground/80">Example measurement list</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                One number per photo
                {targetName ? (
                  <>
                    . Your column name should be <strong>{targetName}</strong>.
                  </>
                ) : (
                  "."
                )}
              </p>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8 text-xs"
              onClick={() => downloadRegressionTemplate(targetName)}
            >
              <Download className="h-3.5 w-3.5 mr-1.5" />
              Download example CSV
            </Button>
          </div>
          <ExampleTable
            headers={["Photo", targetName || "value"]}
            rows={[
              ["part1.jpg", "12.5"],
              ["part2.jpg", "18.0"],
            ]}
          />
        </div>
      )}

      {(taskType === "object_detection" || taskType === "object_localization") && (
        <div className="vd-panel px-5 py-3">
          <Accordion type="single" collapsible className="w-full">
            <AccordionItem value="how" className="border-b-0">
              <AccordionTrigger className="py-2 text-sm hover:no-underline">
                How do I prepare a labeled package?
              </AccordionTrigger>
              <AccordionContent className="text-xs text-muted-foreground space-y-2 pb-3">
                <ol className="list-decimal pl-4 space-y-1.5">
                  <li>Take or collect your photos.</li>
                  <li>
                    Draw boxes around the objects in a labeling tool (Roboflow, Label Studio, or CVAT).
                  </li>
                  <li>Export as a ZIP and upload it here.</li>
                </ol>
                {taskType === "object_localization" && (
                  <p className="text-muted-foreground">Tip: each photo should have only one box.</p>
                )}
              </AccordionContent>
            </AccordionItem>
            <AccordionItem value="sample" className="border-b-0">
              <AccordionTrigger className="py-2 text-sm hover:no-underline">
                Download a tiny example package
              </AccordionTrigger>
              <AccordionContent className="text-xs text-muted-foreground space-y-3 pb-3">
                <p>See the folder layout with one sample photo and one box file.</p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-8 text-xs"
                  onClick={() => downloadDetectionSampleZip()}
                >
                  <Download className="h-3.5 w-3.5 mr-1.5" />
                  Download example ZIP
                </Button>
              </AccordionContent>
            </AccordionItem>
            <AccordionItem value="tools" className="border-b-0">
              <AccordionTrigger className="py-2 text-sm hover:no-underline">
                Supported tools
              </AccordionTrigger>
              <AccordionContent className="text-xs text-muted-foreground pb-3">
                <p>
                  Roboflow, Label Studio, CVAT, and similar tools. Export in YOLO, COCO, or Pascal VOC —
                  VisionDock accepts those packages.
                </p>
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </div>
      )}

      {checklist.length > 0 && (
        <div
          className={`rounded-xl border px-5 py-4 ${
            allDone ? "border-emerald-200 bg-emerald-50/50" : "border-border/60 bg-muted/40"
          }`}
        >
          <div className="flex items-center gap-2 mb-3">
            <Sparkles className={`h-4 w-4 ${allDone ? "text-emerald-600" : "text-muted-foreground"}`} />
            <p className="text-sm font-semibold text-foreground/90">
              {allDone ? "Ready to continue" : "What's left"}
            </p>
          </div>
          <ul className="space-y-2">
            {checklist.map((item) => (
              <li key={item.id} className="flex items-center gap-2 text-sm">
                {item.done ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
                ) : (
                  <Circle className="h-4 w-4 text-muted-foreground/50 shrink-0" />
                )}
                <span className={item.done ? "text-foreground/80" : "text-muted-foreground"}>{item.label}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ExampleTable({ headers, rows }: { headers: string[]; rows: string[][] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border/60">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-muted/40 text-left text-muted-foreground">
            {headers.map((h) => (
              <th key={h} className="px-3 py-2 font-semibold">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-t border-border/40 text-foreground/80">
              {row.map((cell, j) => (
                <td key={j} className="px-3 py-2 font-mono">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
