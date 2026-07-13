// meta: U4 scorecard studio (/scorecard). API-backed via useScorecard: rule
// cards ordered by position with mono rule id chip, dropdown-editable
// SeverityBadge (PATCH severity only), the VERBATIM rule text through
// <RuleText/> (canonical, never flattened), seeded vs custom marker, flag
// count, retrieval keyword chips (primary vs broad, custom rules only), and
// an expandable binary decomposition of editable trigger/requirement check
// cards (save/delete per check, add check). Add rule auto-decomposes server
// side (LLM, ~5-10s): the form shows a "Decomposing rule..." progress state
// and the created rule lands expanded for immediate review. Rule text edits
// offer Save (text only) or Save and regenerate decomposition. Deletes go
// through a confirm dialog; a 409 (flags reference the rule/check, audit
// guard) surfaces the API's detail message verbatim inside the dialog.
// Product note (architecture): edits apply to NEW LIVE checks; corpus runs
// stay on the certified benchmark scorecard.

"use client";

import { useState } from "react";
import Link from "next/link";
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  Loader2,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { SeverityBadge } from "@/components/primitives/severity-badge";
import { RuleText } from "@/lib/render-rule-text";
import { ApiError, type ApiBinaryCheck, type ApiScorecardRule } from "@/lib/api";
import {
  useCreateRule,
  useDeleteCheck,
  useDeleteRule,
  useScorecard,
  useUpdateRule,
  useUpsertCheck,
} from "@/lib/data";
import type { Severity } from "@/lib/types";
import { cn } from "@/lib/utils";

const SEVERITIES = ["High", "Medium", "Low"] as const;

function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.detail : "The API is unreachable.";
}

export default function ScorecardPage() {
  const { data: scorecardRules, isLoading, isError } = useScorecard();
  const [justCreatedId, setJustCreatedId] = useState<string | null>(null);

  return (
    <main className="flex flex-col px-11 pb-14 pt-7">
      <div className="mb-3.5 text-xs text-muted-foreground">
        <Link href="/" className="text-primary hover:underline">
          Dashboard
        </Link>{" "}
        <span className="text-border">›</span> Customize scorecard
      </div>

      <div className="mb-5 flex flex-col gap-1.5">
        <h1 className="text-xl font-medium tracking-tight">
          Customize scorecard
        </h1>
        <p className="text-xs text-muted-foreground">
          Changes apply to new live checks. Corpus runs use the certified
          benchmark scorecard.
        </p>
      </div>

      <AddRuleForm onCreated={setJustCreatedId} />

      {isLoading ? (
        <div className="mt-5 flex flex-col gap-3">
          <div className="h-28 animate-pulse rounded-lg border border-border bg-surface" />
          <div className="h-28 animate-pulse rounded-lg border border-border bg-surface" />
        </div>
      ) : isError ? (
        <p className="mt-5 text-sm text-muted-foreground">
          The API is unreachable.
        </p>
      ) : (
        <div className="mt-5 flex flex-col gap-3.5">
          {(scorecardRules ?? [])
            .slice()
            .sort((a, b) => a.position - b.position)
            .map((rule) => (
              <RuleCard
                key={rule.id}
                rule={rule}
                startExpanded={rule.id === justCreatedId}
              />
            ))}
        </div>
      )}
    </main>
  );
}

/** Add rule: verbatim text + severity. Submitting decomposes server-side
 *  (LLM, ~5-10s), so the button becomes a progress state. */
function AddRuleForm({ onCreated }: { onCreated: (id: string) => void }) {
  const create = useCreateRule();
  const [text, setText] = useState("");
  const [severity, setSeverity] = useState<string>("Medium");
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setError(null);
    try {
      const rule = await create.mutateAsync({
        verbatim_text: text,
        severity,
      });
      setText("");
      setSeverity("Medium");
      onCreated(rule.id);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <div className="rounded-lg border border-border bg-background">
      <div className="border-b border-border/60 bg-surface px-5 py-3">
        <span className="text-[13px] font-semibold">Add rule</span>
      </div>
      <div className="flex flex-col gap-3 p-5">
        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={create.isPending}
          placeholder="Paste the rule exactly as your bank partner wrote it. It is stored verbatim and decomposed into binary checks automatically."
          className="min-h-20 text-[13px]"
        />
        <div className="flex items-center gap-3">
          <Select
            value={severity}
            onValueChange={setSeverity}
            disabled={create.isPending}
          >
            <SelectTrigger size="sm" className="w-[130px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SEVERITIES.map((s) => (
                <SelectItem key={s} value={s} className="text-xs">
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            size="sm"
            className="gap-2"
            disabled={create.isPending || !text.trim()}
            onClick={submit}
          >
            {create.isPending ? (
              <>
                <Loader2 className="size-3.5 animate-spin" />
                Decomposing rule...
              </>
            ) : (
              <>
                <Plus className="size-3.5" />
                Add rule
              </>
            )}
          </Button>
          {create.isPending ? (
            <span className="text-xs text-muted-foreground">
              Generating binary checks and retrieval keywords. This takes a
              few seconds.
            </span>
          ) : null}
          {error ? (
            <span className="text-xs text-danger-text">{error}</span>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function RuleCard({
  rule,
  startExpanded,
}: {
  rule: ApiScorecardRule;
  startExpanded: boolean;
}) {
  const update = useUpdateRule();
  const del = useDeleteRule();
  const [expanded, setExpanded] = useState(startExpanded);
  const [editing, setEditing] = useState(false);
  const [draftText, setDraftText] = useState(rule.verbatim_text);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [regenerating, setRegenerating] = useState(false);
  const [addingCheck, setAddingCheck] = useState(false);

  const keywords = rule.retrieval_keywords ?? {};
  const hasKeywords =
    (keywords.primary?.length ?? 0) > 0 || (keywords.broad?.length ?? 0) > 0;

  async function saveText(regenerate: boolean) {
    setSaveError(null);
    setRegenerating(regenerate);
    try {
      await update.mutateAsync({
        ruleId: rule.id,
        body: { verbatim_text: draftText, regenerate },
      });
      setEditing(false);
    } catch (err) {
      setSaveError(errorMessage(err));
    } finally {
      setRegenerating(false);
    }
  }

  async function deleteRule() {
    setDeleteError(null);
    try {
      await del.mutateAsync(rule.id);
      setConfirmOpen(false);
    } catch (err) {
      setDeleteError(errorMessage(err));
    }
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-background">
      <div className="flex items-center gap-2.5 border-b border-border/60 bg-surface px-5 py-3">
        <span className="rounded-sm border border-border bg-background px-1.5 py-0.5 font-mono text-[11px] font-medium">
          {rule.id}
        </span>
        <Select
          value={rule.severity}
          onValueChange={(v) =>
            update.mutate({ ruleId: rule.id, body: { severity: v } })
          }
        >
          <SelectTrigger
            size="sm"
            className="h-7 gap-1 border-none bg-transparent px-1 shadow-none"
            aria-label="Severity"
          >
            <SeverityBadge severity={rule.severity as Severity} />
          </SelectTrigger>
          <SelectContent>
            {SEVERITIES.map((s) => (
              <SelectItem key={s} value={s} className="text-xs">
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Badge variant="outline" className="font-medium text-muted-foreground">
          {rule.seeded ? "Seeded" : "Custom"}
        </Badge>
        <span className="flex-1 text-xs text-muted-foreground">
          {rule.flag_count}{" "}
          {rule.flag_count === 1 ? "finding" : "findings"} on record
        </span>
        {!editing ? (
          <Button
            variant="ghost"
            size="sm"
            className="gap-1.5 text-muted-foreground"
            onClick={() => {
              setDraftText(rule.verbatim_text);
              setEditing(true);
            }}
          >
            <Pencil className="size-3.5" />
            Edit
          </Button>
        ) : null}
        <Button
          variant="ghost"
          size="sm"
          className="text-muted-foreground"
          onClick={() => {
            setDeleteError(null);
            setConfirmOpen(true);
          }}
          aria-label={`Delete ${rule.id}`}
        >
          <Trash2 className="size-3.5" />
        </Button>
      </div>

      <div className="px-5 py-3.5">
        {editing ? (
          <div className="flex flex-col gap-2.5">
            <Textarea
              value={draftText}
              onChange={(e) => setDraftText(e.target.value)}
              disabled={update.isPending}
              className="min-h-20 text-[13px]"
            />
            <div className="flex items-center gap-2.5">
              <Button
                size="sm"
                variant="outline"
                disabled={update.isPending || !draftText.trim()}
                onClick={() => saveText(false)}
              >
                {update.isPending && !regenerating ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : null}
                Save
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="gap-1.5"
                disabled={update.isPending || !draftText.trim()}
                onClick={() => saveText(true)}
              >
                {regenerating ? (
                  <>
                    <Loader2 className="size-3.5 animate-spin" />
                    Decomposing rule...
                  </>
                ) : (
                  "Save and regenerate decomposition"
                )}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="text-muted-foreground"
                disabled={update.isPending}
                onClick={() => setEditing(false)}
              >
                Cancel
              </Button>
              {saveError ? (
                <span className="text-xs text-danger-text">{saveError}</span>
              ) : null}
            </div>
          </div>
        ) : (
          <p className="text-[13px] leading-relaxed">
            <RuleText text={rule.verbatim_text} />
          </p>
        )}
      </div>

      {hasKeywords ? (
        <div className="border-t border-border/60 px-5 py-3">
          <div className="mb-1.5 text-[11px] font-semibold tracking-wide text-muted-foreground">
            Retrieval keywords
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {(keywords.primary ?? []).map((k) => (
              <span
                key={`p-${k}`}
                className="rounded-pill border border-border bg-surface px-2 py-0.5 font-mono text-[11px] font-medium"
              >
                {k}
              </span>
            ))}
            {(keywords.broad ?? []).length > 0 ? (
              <span className="ml-1 text-[11px] text-muted-foreground">
                broad:
              </span>
            ) : null}
            {(keywords.broad ?? []).map((k) => (
              <span
                key={`b-${k}`}
                className="rounded-pill bg-muted px-2 py-0.5 font-mono text-[11px] text-muted-foreground"
              >
                {k}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      <div className="border-t border-border/60">
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          className="flex w-full items-center gap-1.5 px-5 py-2.5 text-xs font-medium text-muted-foreground hover:text-foreground"
        >
          {expanded ? (
            <ChevronDown className="size-3.5" />
          ) : (
            <ChevronRight className="size-3.5" />
          )}
          Binary decomposition · {rule.checks.length}{" "}
          {rule.checks.length === 1 ? "check" : "checks"}
        </button>
        {expanded ? (
          <div className="flex flex-col gap-2.5 px-5 pb-4">
            {rule.checks.map((check) => (
              <CheckCard key={check.id} ruleId={rule.id} check={check} />
            ))}
            {addingCheck ? (
              <CheckCard
                ruleId={rule.id}
                check={null}
                onDone={() => setAddingCheck(false)}
              />
            ) : (
              <Button
                variant="outline"
                size="sm"
                className="w-fit gap-1.5"
                onClick={() => setAddingCheck(true)}
              >
                <Plus className="size-3.5" />
                Add check
              </Button>
            )}
          </div>
        ) : null}
      </div>

      <ConfirmDeleteDialog
        open={confirmOpen}
        onOpenChange={(o) => {
          setConfirmOpen(o);
          if (!o) setDeleteError(null);
        }}
        title={`Delete rule ${rule.id}?`}
        description="The rule and its binary checks are removed from the scorecard used by new live checks."
        pending={del.isPending}
        error={deleteError}
        onConfirm={deleteRule}
      />
    </div>
  );
}

/** Editable check card. check=null renders the add-check draft (kind
 *  selectable); existing checks keep their kind and edit text + criteria. */
function CheckCard({
  ruleId,
  check,
  onDone,
}: {
  ruleId: string;
  check: ApiBinaryCheck | null;
  onDone?: () => void;
}) {
  const upsert = useUpsertCheck();
  const del = useDeleteCheck();
  const [kind, setKind] = useState<"trigger" | "requirement">(
    check?.kind ?? "requirement"
  );
  const [text, setText] = useState(check?.text ?? "");
  const [criteria, setCriteria] = useState(check?.evidence_criteria ?? "");
  const [error, setError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const dirty =
    check === null ||
    text !== check.text ||
    criteria !== check.evidence_criteria;

  async function save() {
    setError(null);
    try {
      await upsert.mutateAsync({
        checkId: check?.id ?? null,
        ruleId,
        body: { kind, text, evidence_criteria: criteria },
      });
      onDone?.();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function deleteCheck() {
    if (!check) return;
    setDeleteError(null);
    try {
      await del.mutateAsync(check.id);
      setConfirmOpen(false);
    } catch (err) {
      setDeleteError(errorMessage(err));
    }
  }

  return (
    <div
      className={cn(
        "rounded-md border bg-background p-3.5",
        check?.library_entry_id
          ? "border-accent-foreground/25"
          : "border-border"
      )}
    >
      <div className="mb-2.5 flex items-center gap-2">
        {check === null ? (
          <Select
            value={kind}
            onValueChange={(v) => setKind(v as "trigger" | "requirement")}
          >
            <SelectTrigger size="sm" className="w-[140px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="trigger" className="text-xs">
                Trigger
              </SelectItem>
              <SelectItem value="requirement" className="text-xs">
                Requirement
              </SelectItem>
            </SelectContent>
          </Select>
        ) : (
          <>
            <Badge
              variant="outline"
              className="font-medium text-muted-foreground"
            >
              {check.kind === "trigger" ? "Trigger" : "Requirement"}
            </Badge>
            <span className="font-mono text-[11px] text-muted-foreground">
              {check.id}
            </span>
            {check.library_entry_id ? (
              <span className="flex items-center gap-1 text-[11px] text-accent-foreground">
                <BookOpen className="size-3" />
                <span className="font-mono">{check.library_entry_id}</span>
              </span>
            ) : null}
          </>
        )}
        <span className="flex-1" />
        {check !== null ? (
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground"
            onClick={() => {
              setDeleteError(null);
              setConfirmOpen(true);
            }}
            aria-label={`Delete check ${check.id}`}
          >
            <Trash2 className="size-3.5" />
          </Button>
        ) : null}
      </div>
      <div className="flex flex-col gap-2">
        <div>
          <div className="mb-1 text-[11px] font-medium text-muted-foreground">
            Check text
          </div>
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={upsert.isPending}
            placeholder="The binary yes/no question this check asks."
            className="min-h-16 text-[13px]"
          />
        </div>
        <div>
          <div className="mb-1 text-[11px] font-medium text-muted-foreground">
            Evidence criteria
          </div>
          <Textarea
            value={criteria}
            onChange={(e) => setCriteria(e.target.value)}
            disabled={upsert.isPending}
            placeholder="What counts as evidence, and what to quote."
            className="min-h-16 text-[13px]"
          />
        </div>
        <div className="flex items-center gap-2.5">
          <Button
            size="sm"
            variant="outline"
            disabled={upsert.isPending || !dirty || !text.trim()}
            onClick={save}
          >
            {upsert.isPending ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : null}
            Save
          </Button>
          {check === null ? (
            <Button
              size="sm"
              variant="ghost"
              className="text-muted-foreground"
              disabled={upsert.isPending}
              onClick={onDone}
            >
              Cancel
            </Button>
          ) : null}
          {error ? (
            <span className="text-xs text-danger-text">{error}</span>
          ) : null}
        </div>
      </div>

      {check !== null ? (
        <ConfirmDeleteDialog
          open={confirmOpen}
          onOpenChange={(o) => {
            setConfirmOpen(o);
            if (!o) setDeleteError(null);
          }}
          title={`Delete check ${check.id}?`}
          description="The check is removed from the decomposition used by new live checks."
          pending={del.isPending}
          error={deleteError}
          onConfirm={deleteCheck}
        />
      ) : null}
    </div>
  );
}

/** Confirm dialog for destructive actions. A 409 from the audit guard keeps
 *  the dialog open and shows the API's detail message. */
function ConfirmDeleteDialog({
  open,
  onOpenChange,
  title,
  description,
  pending,
  error,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  pending: boolean;
  error: string | null;
  onConfirm: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="text-base">{title}</DialogTitle>
          <DialogDescription className="text-xs">
            {description}
          </DialogDescription>
        </DialogHeader>
        {error ? (
          <p className="rounded-md border border-danger/30 bg-danger-bg px-3 py-2 text-xs text-danger-text">
            {error}
          </p>
        ) : null}
        <DialogFooter>
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground"
            disabled={pending}
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            size="sm"
            disabled={pending}
            onClick={onConfirm}
          >
            {pending ? <Loader2 className="size-3.5 animate-spin" /> : null}
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
