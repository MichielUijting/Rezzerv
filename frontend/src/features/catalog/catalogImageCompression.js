export const CATALOG_IMAGE_MAX_DIMENSION = 640
export const CATALOG_IMAGE_TARGET_BYTES = 280 * 1024
export const CATALOG_IMAGE_HARD_MAX_BYTES = 340 * 1024
const CATALOG_IMAGE_MAX_SOURCE_BYTES = 20 * 1024 * 1024
export const CATALOG_CAMERA_CAPTURE_MAX_DIMENSION = 1280

function dataUrlByteSize(dataUrl) {
  const base64 = String(dataUrl || '').split(',', 2)[1] || ''
  const padding = (base64.match(/=*$/)?.[0]?.length || 0)
  return Math.max(0, Math.floor((base64.length * 3) / 4) - padding)
}

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const image = new Image()
    image.onload = () => {
      URL.revokeObjectURL(url)
      resolve(image)
    }
    image.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('Deze afbeelding kan niet worden gelezen.'))
    }
    image.src = url
  })
}

function renderJpeg(image, maxDimension, quality) {
  const sourceWidth = Number(image.naturalWidth || image.width || 0)
  const sourceHeight = Number(image.naturalHeight || image.height || 0)
  if (!sourceWidth || !sourceHeight) throw new Error('De foto heeft geen geldige afmetingen.')

  const scale = Math.min(1, maxDimension / Math.max(sourceWidth, sourceHeight))
  const width = Math.max(1, Math.round(sourceWidth * scale))
  const height = Math.max(1, Math.round(sourceHeight * scale))
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d')
  if (!context) throw new Error('De foto kan op dit toestel niet worden verwerkt.')

  context.fillStyle = '#ffffff'
  context.fillRect(0, 0, width, height)
  context.drawImage(image, 0, 0, width, height)
  return canvas.toDataURL('image/jpeg', quality)
}

export async function compressCatalogImage(file) {
  if (!(file instanceof Blob)) throw new Error('Selecteer eerst een foto.')
  if (!String(file.type || '').toLowerCase().startsWith('image/')) {
    throw new Error('Selecteer een afbeeldingsbestand.')
  }
  if (Number(file.size || 0) > CATALOG_IMAGE_MAX_SOURCE_BYTES) {
    throw new Error('De geselecteerde foto is te groot om te verwerken.')
  }

  const image = await loadImage(file)
  const dimensions = [CATALOG_IMAGE_MAX_DIMENSION, 512, 384]
  const qualities = [0.82, 0.72, 0.62, 0.52]
  let smallest = ''

  for (const maxDimension of dimensions) {
    for (const quality of qualities) {
      const dataUrl = renderJpeg(image, maxDimension, quality)
      if (!smallest || dataUrlByteSize(dataUrl) < dataUrlByteSize(smallest)) {
        smallest = dataUrl
      }
      if (dataUrlByteSize(dataUrl) <= CATALOG_IMAGE_TARGET_BYTES) return dataUrl
    }
  }

  if (smallest && dataUrlByteSize(smallest) <= CATALOG_IMAGE_HARD_MAX_BYTES) return smallest
  throw new Error('De foto kon niet voldoende worden gecomprimeerd. Kies een andere foto.')
}


export function captureCatalogImageFromVideo(video) {
  const sourceWidth = Number(video?.videoWidth || 0)
  const sourceHeight = Number(video?.videoHeight || 0)
  if (!sourceWidth || !sourceHeight) {
    throw new Error('Het camerabeeld is nog niet klaar. Probeer het opnieuw zodra het beeld zichtbaar is.')
  }

  const scale = Math.min(
    1,
    CATALOG_CAMERA_CAPTURE_MAX_DIMENSION / Math.max(sourceWidth, sourceHeight),
  )
  const width = Math.max(1, Math.round(sourceWidth * scale))
  const height = Math.max(1, Math.round(sourceHeight * scale))
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d')
  if (!context) throw new Error('Het camerabeeld kan op dit toestel niet worden verwerkt.')

  context.drawImage(video, 0, 0, width, height)

  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          reject(new Error('De foto kon niet uit het camerabeeld worden gemaakt.'))
          return
        }
        resolve(blob)
      },
      'image/jpeg',
      0.92,
    )
  })
}
