/**
 * WebAuthn / FIDO2 Browser Utilities
 * Supports:
 * - Roaming Hardware Keys (YubiKey 5 Series, YubiKey Bio, Google Titan, U2F)
 * - Platform Biometrics (Apple Mac Touch ID / Face ID, Windows Hello)
 */

export function bufferToBase64url(buffer) {
  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  return btoa(binary)
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
}

export function base64urlToBuffer(base64url) {
  let base64 = base64url.replace(/-/g, '+').replace(/_/g, '/')
  while (base64.length % 4 !== 0) {
    base64 += '='
  }
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i)
  }
  return bytes.buffer
}

export function isWebAuthnSupported() {
  return typeof window !== 'undefined' &&
    window.PublicKeyCredential !== undefined &&
    typeof window.PublicKeyCredential === 'function'
}

export async function isPlatformAuthenticatorAvailable() {
  if (!isWebAuthnSupported()) return false
  if (typeof PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable !== 'function') {
    return false
  }
  try {
    return await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable()
  } catch {
    return false
  }
}

/**
 * Perform WebAuthn Registration (credential creation).
 * @param {Object} options PublicKeyCredentialCreationOptions from backend
 * @returns {Promise<Object>} Formatted credential payload ready for backend
 */
export async function performWebAuthnRegister(options) {
  if (!isWebAuthnSupported()) {
    throw new Error('WebAuthn / Security Keys are not supported in this browser or context.')
  }

  // Deep clone and transform binary fields
  const publicKey = {
    ...options,
    challenge: base64urlToBuffer(options.challenge),
    user: {
      ...options.user,
      id: base64urlToBuffer(options.user.id),
    },
  }

  if (options.excludeCredentials && Array.isArray(options.excludeCredentials)) {
    publicKey.excludeCredentials = options.excludeCredentials.map(c => ({
      ...c,
      id: base64urlToBuffer(c.id),
    }))
  }

  const credential = await navigator.credentials.create({ publicKey })
  if (!credential) {
    throw new Error('Credential creation was cancelled or returned empty.')
  }

  const response = credential.response
  return {
    id: credential.id,
    rawId: bufferToBase64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: bufferToBase64url(response.clientDataJSON),
      attestationObject: bufferToBase64url(response.attestationObject),
      transports: typeof response.getTransports === 'function' ? response.getTransports() : [],
    },
    authenticatorAttachment: credential.authenticatorAttachment || null,
  }
}

/**
 * Perform WebAuthn Authentication (credential assertion).
 * @param {Object} options PublicKeyCredentialRequestOptions from backend
 * @returns {Promise<Object>} Formatted assertion payload ready for backend
 */
export async function performWebAuthnAuthenticate(options) {
  if (!isWebAuthnSupported()) {
    throw new Error('WebAuthn / Security Keys are not supported in this browser or context.')
  }

  const publicKey = {
    ...options,
    challenge: base64urlToBuffer(options.challenge),
  }

  if (options.allowCredentials && Array.isArray(options.allowCredentials)) {
    publicKey.allowCredentials = options.allowCredentials.map(c => ({
      ...c,
      id: base64urlToBuffer(c.id),
    }))
  }

  const assertion = await navigator.credentials.get({ publicKey })
  if (!assertion) {
    throw new Error('Authentication assertion was cancelled or returned empty.')
  }

  const response = assertion.response
  return {
    id: assertion.id,
    rawId: bufferToBase64url(assertion.rawId),
    type: assertion.type,
    response: {
      clientDataJSON: bufferToBase64url(response.clientDataJSON),
      authenticatorData: bufferToBase64url(response.authenticatorData),
      signature: bufferToBase64url(response.signature),
      userHandle: response.userHandle ? bufferToBase64url(response.userHandle) : null,
    },
  }
}
