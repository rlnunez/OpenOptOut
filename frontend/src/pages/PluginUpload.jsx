import PluginUploadWizard from '../components/PluginUploadWizard'
import { tx } from '../i18n/tx'

// Upload wizard as a page, for users a super admin has granted "can upload
// plugins". They can upload; only a super admin can enable what they upload.
export default function PluginUpload() {
  return (
    <div className="p-4 md:p-6 max-w-2xl">
      <div className="mb-6">
        <h1 className="text-white text-xl font-semibold">{tx("Upload a plugin")}</h1>
        <p className="text-slate-400 text-sm mt-0.5">
          {tx("Plugins you upload are installed disabled. A super admin reviews and enables them.")}
        </p>
      </div>
      <PluginUploadWizard asPage />
    </div>
  )
}
