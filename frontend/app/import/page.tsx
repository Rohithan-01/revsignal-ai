"use client";

import Link from "next/link";
import { useRef, useState, type DragEvent, type ChangeEvent } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, ArrowRight, CheckCircle2, CloudUpload, Download, FileCheck2, FileSpreadsheet, LoaderCircle, X } from "lucide-react";
import { useRevenueData } from "@/components/data-provider";
import { api } from "@/lib/api";
import type { UploadResponse } from "@/lib/types";

const MAX_FILE_SIZE = 10 * 1024 * 1024;
const REQUIRED_FIELDS: Record<string, string[]> = {
  deal_id: ["deal_id", "dealid", "opportunity_id", "id", "deal"],
  account_name: ["account_name", "account", "company", "customer_name", "customer"],
  deal_value: ["deal_value", "amount", "value", "revenue", "opportunity_value"],
  stage: ["stage", "sales_stage", "deal_stage", "pipeline_stage"],
  status: ["status", "deal_status", "opportunity_status"],
};

function firstCsvRow(text: string): string[] {
  const fields: string[] = [];
  let current = "";
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (char === '"') {
      if (quoted && text[index + 1] === '"') {
        current += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (char === "," && !quoted) {
      fields.push(current.trim().toLowerCase().replace(/ /g, "_"));
      current = "";
    } else if ((char === "\n" || char === "\r") && !quoted) {
      break;
    } else {
      current += char;
    }
  }
  fields.push(current.trim().toLowerCase().replace(/ /g, "_"));
  return fields;
}

function validateHeaders(text: string): string[] {
  if (!text.trim()) return ["This CSV file is empty."];
  const header = firstCsvRow(text);
  const missing = Object.entries(REQUIRED_FIELDS)
    .filter(([, aliases]) => !header.some((column) => aliases.includes(column)))
    .map(([field]) => field);
  return missing.length ? [`Missing required columns: ${missing.join(", ")}.`] : [];
}

export default function ImportPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();
  const { refresh } = useRevenueData();
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [result, setResult] = useState<UploadResponse | null>(null);

  async function selectFile(candidate: File | undefined) {
    setErrors([]);
    setResult(null);
    setFile(null);
    if (!candidate) return;
    if (!candidate.name.toLowerCase().endsWith(".csv")) {
      setErrors(["Unsupported file type. Choose a .csv file."]);
      return;
    }
    if (candidate.size > MAX_FILE_SIZE) {
      setErrors(["This file exceeds the 10 MB limit. Choose a smaller CSV file."]);
      return;
    }
    if (!candidate.size) {
      setErrors(["This CSV file is empty."]);
      return;
    }
    const headerErrors = validateHeaders(await candidate.slice(0, 64 * 1024).text());
    if (headerErrors.length) {
      setErrors(headerErrors);
      return;
    }
    setFile(candidate);
  }

  function onInputChange(event: ChangeEvent<HTMLInputElement>) {
    void selectFile(event.target.files?.[0]);
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    void selectFile(event.dataTransfer.files[0]);
  }

  async function upload() {
    if (!file || uploading) return;
    setUploading(true);
    setErrors([]);
    setResult(null);
    try {
      const response = await api.upload(file);
      setResult(response);
      await refresh();
    } catch (reason) {
      setErrors([reason instanceof Error ? reason.message : "Upload failed. Check the file and try again."]);
    } finally {
      setUploading(false);
    }
  }

  return (
    <>
      <div className="page-heading">
        <div><div className="eyebrow"><span className="eyebrow-dot" /> PIPELINE DATA</div><h1>Import CRM data</h1><p>Bring your pipeline into focus with a clean CRM export.</p></div>
        <Link href="/sample_crm.csv" download className="button button-secondary"><Download size={15} /> Download sample CSV</Link>
      </div>

      <div className="import-layout">
        <section className="panel import-main">
          <div className="import-section-heading"><div><h2>Upload a CSV file</h2><p>Deal records will be validated and scored after import.</p></div><span className="import-step">STEP 01 <i /> STEP 02</span></div>
          <div
            className={`dropzone${dragging ? " dropzone-active" : ""}${file ? " dropzone-has-file" : ""}`}
            onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
            onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false); }}
            onDrop={onDrop}
          >
            <input ref={inputRef} className="sr-only" type="file" accept=".csv,text/csv" onChange={onInputChange} aria-label="Choose a CRM CSV file" />
            {file ? (
              <><div className="dropzone-icon file-icon"><FileCheck2 size={21} /></div><strong>{file.name}</strong><span>{(file.size / 1024).toFixed(1)} KB · Ready to validate</span><button className="file-remove" aria-label="Remove selected file" onClick={() => { setFile(null); setResult(null); if (inputRef.current) inputRef.current.value = ""; }}><X size={15} /></button></>
            ) : (
              <><div className="dropzone-icon"><CloudUpload size={22} /></div><strong>Drop your CSV file here</strong><span>or <button className="browse-link" onClick={() => inputRef.current?.click()}>browse files</button> from your computer</span><small>CSV only · Maximum file size 10 MB</small></>
            )}
          </div>
          <div className="upload-requirement-line"><FileSpreadsheet size={15} /><span>Required columns:</span><code>deal_id</code><code>account_name</code><code>deal_value</code><code>stage</code><code>status</code></div>

          {errors.length > 0 && <div className="upload-alert upload-error" role="alert"><AlertCircle size={17} /><div><strong>We couldn’t import this file</strong>{errors.map((message) => <p key={message}>{message}</p>)}</div></div>}
          {uploading && <div className="upload-alert upload-progress" role="status"><LoaderCircle className="spin" size={17} /><div><strong>Importing your data…</strong><p>Validating rows and calculating explainable risk scores.</p></div></div>}
          {result && <div className="upload-alert upload-success" role="status"><CheckCircle2 size={18} /><div><strong>Import complete</strong><p>{result.message} Your live pipeline is ready to review.</p><button className="text-link" onClick={() => router.push("/deals")}>View imported deals <ArrowRight size={14} /></button></div></div>}

          {!result && <button className="button button-primary import-submit" disabled={!file || uploading} onClick={() => void upload()}>{uploading ? <><LoaderCircle className="spin" size={15} /> Importing…</> : <>Validate & import <ArrowRight size={15} /></>}</button>}
          <div className="import-security-note"><CheckCircle2 size={14} /> Your CSV is processed by your local RevSignal backend. It is not sent to an external service.</div>
        </section>

        <aside className="import-aside">
          <section className="panel import-guide">
            <div className="import-guide-icon"><FileSpreadsheet size={17} /></div><h2>Prepare your export</h2><p>Export opportunities from your CRM as a CSV file. RevSignal accepts common column names and aliases.</p>
            <div className="field-guide-title">Required fields</div>
            <div className="field-guide-list"><div><code>deal_id</code><span>Unique deal identifier</span></div><div><code>account_name</code><span>Company or account name</span></div><div><code>deal_value</code><span>Non-negative numeric value</span></div><div><code>stage</code><span>Current sales stage</span></div><div><code>status</code><span>Open, won, or lost</span></div></div>
            <div className="import-guide-footer"><Link href="/sample_crm.csv" download><Download size={14} /> Get the sample template</Link></div>
          </section>
          <div className="import-note"><AlertCircle size={15} /><span>Deals with an existing ID are updated on import. Duplicate IDs within the same file are rejected to avoid ambiguous records.</span></div>
        </aside>
      </div>
    </>
  );
}
