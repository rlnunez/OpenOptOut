import React, { useState, useEffect } from 'react'
import { Globe, Plus, Check, Save, RotateCcw, Search, Filter, AlertCircle, CheckCircle2, ArrowRight } from 'lucide-react'
import api from '../api'
import { useLanguage } from '../i18n/LanguageContext'

export default function Translations() {
  const { language: currentAppLang, setLanguage: setAppLanguage, allLanguages, refreshLanguages, t } = useLanguage()

  const [selectedLang, setSelectedLang] = useState('es')
  const [dictionary, setDictionary] = useState([])
  const [translations, setTranslations] = useState({})
  const [originalTranslations, setOriginalTranslations] = useState({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [search, setSearch] = useState('')
  const [selectedLocation, setSelectedLocation] = useState('all')

  // New Language Modal State
  const [showAddModal, setShowAddModal] = useState(false)
  const [newCode, setNewCode] = useState('')
  const [newName, setNewName] = useState('')
  const [newNativeName, setNewNativeName] = useState('')
  const [newIsRTL, setNewIsRTL] = useState(false)
  const [addError, setAddError] = useState('')

  // Load master dictionary (keys, default text, locations, descriptions)
  useEffect(() => {
    api.get('/i18n/dictionary')
      .then(res => setDictionary(res.data || []))
      .catch(err => console.error('Failed to load translation dictionary', err))
  }, [])

  // Load translations for selected language
  const loadTranslations = async (code) => {
    setLoading(true)
    setSaveSuccess(false)
    try {
      const res = await api.get(`/i18n/translations/${code}`)
      const trans = res.data?.translations || {}
      setTranslations({ ...trans })
      setOriginalTranslations({ ...trans })
    } catch (e) {
      console.error('Failed to load translations', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (selectedLang) {
      loadTranslations(selectedLang)
    }
  }, [selectedLang])

  // Extract unique locations for filtering
  const locations = ['all', ...Array.from(new Set(dictionary.map(d => d.location).filter(Boolean)))]

  // Filter dictionary items
  const filteredItems = dictionary.filter(item => {
    const matchesLoc = selectedLocation === 'all' || item.location === selectedLocation
    const q = search.toLowerCase()
    const matchesSearch = !q ||
      item.key.toLowerCase().includes(q) ||
      (item.default_text || '').toLowerCase().includes(q) ||
      (translations[item.key] || '').toLowerCase().includes(q) ||
      (item.location || '').toLowerCase().includes(q)
    return matchesLoc && matchesSearch
  })

  // Handle text edit
  const handleChangeText = (key, val) => {
    setTranslations(prev => ({ ...prev, [key]: val }))
    setSaveSuccess(false)
  }

  // Save changes to backend
  const handleSave = async () => {
    setSaving(true)
    setSaveSuccess(false)
    try {
      await api.put(`/i18n/translations/${selectedLang}`, {
        translations
      })
      setOriginalTranslations({ ...translations })
      setSaveSuccess(true)
      // If we updated the currently active app language, refresh app state
      if (selectedLang.toLowerCase() === currentAppLang.toLowerCase()) {
        setAppLanguage(selectedLang)
      }
      setTimeout(() => setSaveSuccess(false), 3000)
    } catch (e) {
      alert('Failed to save translations: ' + (e.response?.data?.detail || e.message))
    } finally {
      setSaving(false)
    }
  }

  // Toggle language enabled status
  const handleToggleLanguage = async (code, currentEnabled) => {
    try {
      await api.put(`/i18n/languages/${code}/toggle`, { enabled: !currentEnabled })
      await refreshLanguages()
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to toggle language')
    }
  }

  // Register new language
  const handleAddLanguage = async (e) => {
    e.preventDefault()
    setAddError('')
    if (!newCode.trim() || !newName.trim()) {
      setAddError('Language code and English name are required.')
      return
    }
    try {
      await api.post('/i18n/languages', {
        code: newCode.trim().toLowerCase(),
        name: newName.trim(),
        native_name: newNativeName.trim() || newName.trim(),
        is_rtl: newIsRTL,
      })
      await refreshLanguages()
      setSelectedLang(newCode.trim().toLowerCase())
      setShowAddModal(false)
      setNewCode('')
      setNewName('')
      setNewNativeName('')
      setNewIsRTL(false)
    } catch (err) {
      setAddError(err.response?.data?.detail || 'Failed to add language')
    }
  }

  const activeLangObj = allLanguages.find(l => l.code === selectedLang) || { is_rtl: false }
  const isSelectedLangRTL = Boolean(activeLangObj.is_rtl)

  // Count modified items
  const dirtyCount = Object.keys(translations).filter(k => translations[k] !== originalTranslations[k]).length

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Page Title & Language Selector */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2.5">
            <Globe className="text-blue-400" size={26} />
            {t('i18n.manager_title', 'Internationalization & Translation Manager')}
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            {t('i18n.manager_desc', 'Manage available interface languages, customize terminology, and inspect where wording appears.')}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowAddModal(true)}
            className="px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-xl text-xs font-medium flex items-center gap-1.5 transition-colors"
          >
            <Plus size={15} />
            <span>{t('i18n.add_language', 'Add Language')}</span>
          </button>

          <button
            onClick={handleSave}
            disabled={saving || dirtyCount === 0}
            className={`px-4 py-2 rounded-xl text-xs font-medium flex items-center gap-1.5 transition-all shadow-xs ${
              dirtyCount > 0
                ? 'bg-blue-600 hover:bg-blue-500 text-white'
                : 'bg-slate-800 text-slate-500 border border-slate-800 cursor-not-allowed'
            }`}
          >
            <Save size={15} />
            <span>{saving ? 'Saving...' : saveSuccess ? 'Saved!' : `Save Translations (${dirtyCount})`}</span>
          </button>
        </div>
      </div>

      {saveSuccess && (
        <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-sm flex items-center gap-2 animate-in fade-in">
          <CheckCircle2 size={18} />
          <span>Translations saved successfully and live on the platform!</span>
        </div>
      )}

      {/* Language Switcher Tabs & Toggles */}
      <div className="space-y-3">
        <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
          {t('i18n.active_languages', 'Configured Languages')}
        </div>
        <div className="flex flex-wrap gap-2">
          {allLanguages.map((lang) => {
            const isSelected = selectedLang === lang.code
            return (
              <div
                key={lang.code}
                className={`flex items-center rounded-xl border transition-all ${
                  isSelected
                    ? 'border-blue-500 bg-blue-500/10 text-white shadow-xs ring-1 ring-blue-500/40'
                    : 'border-slate-800 bg-slate-900/60 text-slate-300 hover:border-slate-700'
                }`}
              >
                <button
                  onClick={() => setSelectedLang(lang.code)}
                  className="px-3.5 py-2 text-start flex items-center gap-2"
                >
                  <span className="font-semibold text-sm">{lang.native_name}</span>
                  <span className="text-xs text-slate-400">({lang.code})</span>
                  {lang.is_rtl && (
                    <span className="text-[10px] px-1.5 py-0.2 rounded-sm bg-amber-500/15 text-amber-300 border border-amber-500/20 font-mono">
                      RTL
                    </span>
                  )}
                </button>

                {/* Enable/Disable toggle */}
                {lang.code !== 'en' && (
                  <button
                    onClick={() => handleToggleLanguage(lang.code, lang.enabled)}
                    title={lang.enabled ? 'Click to disable' : 'Click to enable'}
                    className={`px-2 py-1 mr-2 text-[10px] rounded-lg font-medium transition-colors ${
                      lang.enabled
                        ? 'bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30'
                        : 'bg-slate-800 text-slate-500 hover:bg-slate-700'
                    }`}
                  >
                    {lang.enabled ? 'Active' : 'Off'}
                  </button>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row gap-3 pt-2">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search keys, original text, or translations..."
            className="w-full pl-10 pr-4 py-2 bg-slate-900 border border-slate-800 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-hidden focus:border-blue-500"
          />
        </div>

        <div className="relative">
          <select
            value={selectedLocation}
            onChange={(e) => setSelectedLocation(e.target.value)}
            className="w-full sm:w-64 px-3.5 py-2 bg-slate-900 border border-slate-800 rounded-xl text-sm text-slate-300 focus:outline-hidden focus:border-blue-500"
          >
            {locations.map(loc => (
              <option key={loc} value={loc}>
                {loc === 'all' ? 'All Screen Locations' : loc}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Translation Replacement Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/60">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-white">
              Editing: <span className="text-blue-400 capitalize">{activeLangObj.name || selectedLang}</span>
            </span>
            {isSelectedLangRTL && (
              <span className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-full">
                Right-to-Left (RTL) Input
              </span>
            )}
          </div>
          <span className="text-xs text-slate-400">
            Showing {filteredItems.length} of {dictionary.length} strings
          </span>
        </div>

        {loading ? (
          <div className="p-12 text-center text-slate-500 text-sm">
            Loading translation keys...
          </div>
        ) : filteredItems.length === 0 ? (
          <div className="p-12 text-center text-slate-500 text-sm">
            No translation keys matched your search or location filter.
          </div>
        ) : (
          <div className="divide-y divide-slate-800/80">
            {filteredItems.map(item => {
              const currentVal = translations[item.key] ?? item.default_text
              const isDirty = translations[item.key] !== originalTranslations[item.key]

              return (
                <div key={item.key} className="p-4 hover:bg-slate-850 transition-colors space-y-2.5">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-semibold text-slate-300 bg-slate-950 px-2 py-0.5 rounded-sm border border-slate-800">
                        {item.key}
                      </span>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-300 border border-blue-500/20">
                        {item.location}
                      </span>
                    </div>
                    {item.description && (
                      <span className="text-xs text-slate-500 italic">
                        {item.description}
                      </span>
                    )}
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                    {/* Source English */}
                    <div className="p-2.5 bg-slate-950/60 border border-slate-800 rounded-xl">
                      <div className="text-[10px] uppercase font-bold text-slate-500 mb-1">
                        Source (English)
                      </div>
                      <div className="text-sm text-slate-300 select-all">
                        {item.default_text}
                      </div>
                    </div>

                    {/* Target Replacement Input */}
                    <div>
                      <div className="flex items-center justify-between text-[10px] uppercase font-bold text-slate-500 mb-1">
                        <span>{activeLangObj.name} Translation / Override</span>
                        {isDirty && <span className="text-blue-400">Modified</span>}
                      </div>
                      <input
                        type="text"
                        dir={isSelectedLangRTL ? 'rtl' : 'ltr'}
                        value={currentVal}
                        onChange={(e) => handleChangeText(item.key, e.target.value)}
                        placeholder={item.default_text}
                        className={`w-full px-3 py-2 bg-slate-950 border rounded-xl text-sm text-white placeholder-slate-600 focus:outline-hidden transition-colors ${
                          isDirty
                            ? 'border-blue-500 bg-blue-950/20'
                            : 'border-slate-800 focus:border-slate-700'
                        } ${isSelectedLangRTL ? 'text-right font-arabic' : 'text-left'}`}
                      />
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Add New Language Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-xs animate-in fade-in">
          <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-6 space-y-4">
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              <Globe size={18} className="text-blue-400" />
              <span>Register New Language</span>
            </h3>

            {addError && (
              <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-xs text-red-300">
                {addError}
              </div>
            )}

            <form onSubmit={handleAddLanguage} className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">
                  Language Code (ISO 639-1)
                </label>
                <input
                  type="text"
                  placeholder="e.g. it, pt-br, ja, de"
                  value={newCode}
                  onChange={(e) => setNewCode(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-xl text-sm text-white focus:outline-hidden focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">
                  English Name
                </label>
                <input
                  type="text"
                  placeholder="e.g. Italian"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-xl text-sm text-white focus:outline-hidden focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">
                  Native Display Name
                </label>
                <input
                  type="text"
                  placeholder="e.g. Italiano"
                  value={newNativeName}
                  onChange={(e) => setNewNativeName(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-xl text-sm text-white focus:outline-hidden focus:border-blue-500"
                />
              </div>

              <div className="flex items-center gap-2 pt-2">
                <input
                  type="checkbox"
                  id="newIsRTL"
                  checked={newIsRTL}
                  onChange={(e) => setNewIsRTL(e.target.checked)}
                  className="rounded-sm border-slate-800 bg-slate-950 text-blue-600 focus:ring-0"
                />
                <label htmlFor="newIsRTL" className="text-xs text-slate-300">
                  Right-to-Left (RTL) Script (e.g. Arabic, Hebrew, Urdu)
                </label>
              </div>

              <div className="flex items-center justify-end gap-2 pt-4">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 rounded-xl text-xs text-slate-400 hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium"
                >
                  Register Language
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
