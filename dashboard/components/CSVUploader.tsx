"use client";

import { useState, useRef } from 'react';
import { Upload, FileSpreadsheet, Loader2, CheckCircle, AlertCircle, X } from 'lucide-react';

interface CSVUploaderProps {
  onUploadSuccess: () => void;
}

export default function CSVUploader({ onUploadSuccess }: CSVUploaderProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [result, setResult] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = async (file: File) => {
    if (!file.name.endsWith('.csv')) {
      setResult({ type: 'error', message: 'Please upload a .csv file' });
      return;
    }

    setIsUploading(true);
    setResult(null);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('campaignId', `campaign_${Date.now()}`);

      const res = await fetch('/api/leads', {
        method: 'POST',
        body: formData,
      });

      const data = await res.json();

      if (res.ok) {
        setResult({ type: 'success', message: data.message || `${data.count} leads imported!` });
        onUploadSuccess();
      } else {
        setResult({ type: 'error', message: data.error || 'Upload failed' });
      }
    } catch (err: any) {
      setResult({ type: 'error', message: err.message || 'Network error' });
    } finally {
      setIsUploading(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  return (
    <div className="space-y-4">
      {/* Drop Zone */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => fileInputRef.current?.click()}
        className={`
          relative border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-300
          ${isDragging
            ? 'border-blue-500 bg-blue-500/10 scale-[1.02]'
            : 'border-white/10 bg-white/[0.02] hover:border-white/20 hover:bg-white/[0.04]'
          }
        `}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
          }}
        />

        {isUploading ? (
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="w-10 h-10 text-blue-400 animate-spin" />
            <p className="text-sm text-gray-400">Uploading & parsing CSV...</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-500/20 to-purple-500/20 flex items-center justify-center">
              <Upload className="w-7 h-7 text-blue-400" />
            </div>
            <div>
              <p className="text-sm text-white font-medium">Drop CSV file here or click to browse</p>
              <p className="text-xs text-gray-500 mt-1">Columns: Business Name, Phone Number</p>
            </div>
          </div>
        )}
      </div>

      {/* Result Message */}
      {result && (
        <div className={`flex items-center gap-2 p-3 rounded-lg text-sm animate-in fade-in slide-in-from-top-2 ${
          result.type === 'success'
            ? 'bg-green-500/10 text-green-300 border border-green-500/20'
            : 'bg-red-500/10 text-red-300 border border-red-500/20'
        }`}>
          {result.type === 'success' ? (
            <CheckCircle className="w-4 h-4 shrink-0" />
          ) : (
            <AlertCircle className="w-4 h-4 shrink-0" />
          )}
          <span className="flex-1">{result.message}</span>
          <button onClick={() => setResult(null)} className="hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  );
}
