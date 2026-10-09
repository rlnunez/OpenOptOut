import React, { useState } from 'react'
import { Globe, User, Mail, Compass, CheckCircle2, ChevronRight, ChevronLeft, X, Shield, Lock, ArrowRight } from 'lucide-react'
import { useLanguage } from '../i18n/LanguageContext'
import api from '../api'

export default function UserWelcomeModal() {
  const { language, setLanguage, availableLanguages, isRTL, t, showWelcomeTour, completeWelcomeTour } = useLanguage()
  const [step, setStep] = useState(1)
  const totalSteps = 4

  // Form states for quick PII setup
  const [fullName, setFullName] = useState('')
  const [city, setCity] = useState('')
  const [state, setState] = useState('')
  const [address, setAddress] = useState('')
  const [phone, setPhone] = useState('')
  const [piiSaving, setPiiSaving] = useState(false)
  const [piiSaved, setPiiSaved] = useState(false)

  if (!showWelcomeTour) return null

  const handleSavePii = async () => {
    if (!fullName.trim() && !address.trim()) return
    setPiiSaving(true)
    try {
      // Fetch or create primary member profile
      const membersRes = await api.get('/family')
      let memberId = null
      if (Array.isArray(membersRes.data) && membersRes.data.length > 0) {
        memberId = membersRes.data[0].id
      }

      if (memberId) {
        if (fullName.trim()) {
          await api.post(`/family/${memberId}/identities`, { kind: 'name', value: fullName.trim() })
        }
        if (address.trim() || city.trim()) {
          const fullAddr = [address, city, state].filter(Boolean).join(', ')
          await api.post(`/family/${memberId}/identities`, { kind: 'address', value: fullAddr })
        }
        if (phone.trim()) {
          await api.post(`/family/${memberId}/identities`, { kind: 'phone', value: phone.trim() })
        }
      }
      setPiiSaved(true)
    } catch (e) {
      console.warn('Could not save identity info during onboarding:', e)
    } finally {
      setPiiSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-xs animate-in fade-in duration-200">
      <div className="relative w-full max-w-2xl bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col">
        {/* Top Header */}
        <div className="px-6 py-5 border-b border-slate-800 flex items-center justify-between bg-slate-900/50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-600/20 border border-blue-500/30 flex items-center justify-center text-blue-400">
              <Shield size={20} />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">
                {t('tutorial.welcome_title', 'Welcome to OpenOptOut')}
              </h2>
              <p className="text-xs text-slate-400">
                {t('tutorial.welcome_desc', "Let's take a moment to customize your experience and configure your privacy protections.")}
              </p>
            </div>
          </div>
          <button
            onClick={completeWelcomeTour}
            className="text-slate-400 hover:text-white p-2 rounded-lg hover:bg-slate-800 transition-colors"
            title={t('tutorial.skip', 'Skip Tutorial')}
          >
            <X size={18} />
          </button>
        </div>

        {/* Progress Bar */}
        <div className="px-6 py-3 bg-slate-950/60 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            {[1, 2, 3, 4].map(s => (
              <div
                key={s}
                className={`h-2 rounded-full transition-all duration-300 ${
                  s === step ? 'w-8 bg-blue-500' : s < step ? 'w-5 bg-blue-600/50' : 'w-5 bg-slate-800'
                }`}
              />
            ))}
          </div>
          <span className="text-xs font-medium text-slate-400">
            Step {step} of {totalSteps}
          </span>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto max-h-[60vh] space-y-6">
          {/* STEP 1: LANGUAGE SELECTION */}
          {step === 1 && (
            <div className="space-y-4 animate-in fade-in duration-150">
              <div className="flex items-center gap-2.5 text-blue-400">
                <Globe size={18} />
                <h3 className="text-base font-medium text-white">
                  {t('tutorial.lang_step_title', 'Choose Your Preferred Language')}
                </h3>
              </div>
              <p className="text-sm text-slate-300">
                {t('tutorial.lang_step_desc', 'Select your language below. The interface, notifications, and layout will adapt immediately.')}
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                {availableLanguages.map((lang) => {
                  const isSelected = language.toLowerCase() === lang.code.toLowerCase()
                  return (
                    <button
                      key={lang.code}
                      onClick={() => setLanguage(lang.code)}
                      className={`p-3.5 rounded-xl border text-start flex items-center justify-between transition-all ${
                        isSelected
                          ? 'border-blue-500 bg-blue-500/10 text-white shadow-xs ring-1 ring-blue-500/50'
                          : 'border-slate-800 bg-slate-950/50 text-slate-300 hover:border-slate-700 hover:bg-slate-800/40'
                      }`}
                    >
                      <div className="flex flex-col">
                        <span className="font-semibold text-sm">{lang.native_name}</span>
                        <span className="text-xs text-slate-400">{lang.name}</span>
                      </div>
                      {lang.is_rtl && (
                        <span className="text-[10px] px-2 py-0.5 rounded-sm bg-amber-500/10 text-amber-300 border border-amber-500/20 font-mono">
                          RTL
                        </span>
                      )}
                      {isSelected && <CheckCircle2 size={16} className="text-blue-400" />}
                    </button>
                  )
                })}
              </div>

              {isRTL && (
                <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl text-xs text-amber-200 flex items-center gap-2">
                  <span>ℹ️</span>
                  <span>Right-to-Left (RTL) mode is automatically enabled for this language.</span>
                </div>
              )}
            </div>
          )}

          {/* STEP 2: IDENTITY VAULT SETUP */}
          {step === 2 && (
            <div className="space-y-4 animate-in fade-in duration-150">
              <div className="flex items-center gap-2.5 text-blue-400">
                <User size={18} />
                <h3 className="text-base font-medium text-white">
                  {t('tutorial.pii_step_title', 'Protect Your Identity')}
                </h3>
              </div>
              <p className="text-sm text-slate-300">
                {t('tutorial.pii_step_desc', 'Provide your name and city/state so automated agents can locate and scrub your listings.')}
              </p>

              <div className="space-y-3 bg-slate-950/40 p-4 rounded-xl border border-slate-800/80">
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1">Full Legal Name</label>
                  <input
                    type="text"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="e.g. Jane Doe"
                    className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-hidden focus:border-blue-500"
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">City</label>
                    <input
                      type="text"
                      value={city}
                      onChange={(e) => setCity(e.target.value)}
                      placeholder="e.g. Seattle"
                      className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-hidden focus:border-blue-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1">State / Province</label>
                    <input
                      type="text"
                      value={state}
                      onChange={(e) => setState(e.target.value)}
                      placeholder="e.g. WA"
                      className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-hidden focus:border-blue-500"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1">Street Address (Optional)</label>
                  <input
                    type="text"
                    value={address}
                    onChange={(e) => setAddress(e.target.value)}
                    placeholder="e.g. 123 Pine St"
                    className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-hidden focus:border-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1">Phone Number (Optional)</label>
                  <input
                    type="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="e.g. (206) 555-0199"
                    className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-hidden focus:border-blue-500"
                  />
                </div>

                <div className="flex items-center justify-between pt-2">
                  <div className="flex items-center gap-1.5 text-xs text-slate-400">
                    <Lock size={12} className="text-emerald-400" />
                    <span>Encrypted with AES-256 at rest</span>
                  </div>
                  <button
                    onClick={handleSavePii}
                    disabled={piiSaving || (!fullName && !address)}
                    className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg text-xs font-medium transition-colors"
                  >
                    {piiSaving ? 'Saving...' : piiSaved ? '✓ Saved to Vault' : 'Save to Vault'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* STEP 3: EMAIL COMMUNICATIONS */}
          {step === 3 && (
            <div className="space-y-4 animate-in fade-in duration-150">
              <div className="flex items-center gap-2.5 text-blue-400">
                <Mail size={18} />
                <h3 className="text-base font-medium text-white">
                  {t('tutorial.email_step_title', 'Opt-Out Communications')}
                </h3>
              </div>
              <p className="text-sm text-slate-300">
                {t('tutorial.email_step_desc', 'OpenOptOut dispatches removal requests using dedicated inboxes and monitors broker responses.')}
              </p>

              <div className="space-y-3">
                <div className="p-4 rounded-xl border border-slate-800 bg-slate-950/60 flex items-start gap-3">
                  <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 shrink-0">
                    <Shield size={18} />
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-white">Centralized Automated Inbox</h4>
                    <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                      By default, opt-out requests are sent from your organization's configured mail transport. Inbound confirmation links are captured and honored automatically in the background.
                    </p>
                  </div>
                </div>

                <div className="p-4 rounded-xl border border-slate-800 bg-slate-950/60 flex items-start gap-3">
                  <div className="p-2 rounded-lg bg-blue-500/10 text-blue-400 shrink-0">
                    <CheckCircle2 size={18} />
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-white">Zero Mailbox Clutter</h4>
                    <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                      You won't receive hundreds of data broker marketing emails or spam. Only final verification status changes are reported on your dashboard.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* STEP 4: PLATFORM TOUR & QUICK OVERVIEW */}
          {step === 4 && (
            <div className="space-y-4 animate-in fade-in duration-150">
              <div className="flex items-center gap-2.5 text-blue-400">
                <Compass size={18} />
                <h3 className="text-base font-medium text-white">
                  {t('tutorial.tour_step_title', 'Platform Tour & Quick Navigation')}
                </h3>
              </div>
              <p className="text-sm text-slate-300">
                {t('tutorial.tour_step_desc', 'Explore your dashboard to view verified removals, manage family profiles, and monitor broker health.')}
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                <div className="p-3.5 rounded-xl border border-slate-800 bg-slate-950/50 space-y-1">
                  <div className="flex items-center gap-2 font-medium text-sm text-white">
                    <span className="text-blue-400">📊</span>
                    <span>Dashboard</span>
                  </div>
                  <p className="text-xs text-slate-400">
                    View real-time removal rates, active scan records, and overall protection coverage.
                  </p>
                </div>

                <div className="p-3.5 rounded-xl border border-slate-800 bg-slate-950/50 space-y-1">
                  <div className="flex items-center gap-2 font-medium text-sm text-white">
                    <span className="text-purple-400">🔐</span>
                    <span>Identity Vault</span>
                  </div>
                  <p className="text-xs text-slate-400">
                    Add prior addresses, maiden names, and relative records to maximize data scrubbing.
                  </p>
                </div>

                <div className="p-3.5 rounded-xl border border-slate-800 bg-slate-950/50 space-y-1">
                  <div className="flex items-center gap-2 font-medium text-sm text-white">
                    <span className="text-amber-400">⚡</span>
                    <span>Removal Requests</span>
                  </div>
                  <p className="text-xs text-slate-400">
                    Track the progress of requests submitted across major brokers (Spokeo, Radaris, Whitepages, etc.).
                  </p>
                </div>

                <div className="p-3.5 rounded-xl border border-slate-800 bg-slate-950/50 space-y-1">
                  <div className="flex items-center gap-2 font-medium text-sm text-white">
                    <span className="text-emerald-400">🌐</span>
                    <span>Language Picker</span>
                  </div>
                  <p className="text-xs text-slate-400">
                    Switch your interface language anytime from the menu bar with full RTL and LTR support.
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer Navigation */}
        <div className="px-6 py-4 border-t border-slate-800 bg-slate-900/80 flex items-center justify-between">
          <button
            onClick={completeWelcomeTour}
            className="text-xs text-slate-400 hover:text-white transition-colors"
          >
            {t('tutorial.skip', 'Skip Tutorial')}
          </button>

          <div className="flex items-center gap-2">
            {step > 1 && (
              <button
                onClick={() => setStep(step - 1)}
                className="px-4 py-2 rounded-xl border border-slate-700 bg-slate-800 hover:bg-slate-700 text-white text-xs font-medium flex items-center gap-1.5 transition-colors"
              >
                {isRTL ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
                <span>{t('common.back', 'Back')}</span>
              </button>
            )}

            {step < totalSteps ? (
              <button
                onClick={() => setStep(step + 1)}
                className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium flex items-center gap-1.5 transition-colors shadow-xs"
              >
                <span>{t('common.next', 'Next')}</span>
                {isRTL ? <ChevronLeft size={14} /> : <ChevronRight size={14} />}
              </button>
            ) : (
              <button
                onClick={completeWelcomeTour}
                className="px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium flex items-center gap-1.5 transition-colors shadow-xs"
              >
                <span>{t('tutorial.start_protecting', 'Start Protecting My Data')}</span>
                <ArrowRight size={14} />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
