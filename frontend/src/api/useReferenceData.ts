import { useContext } from 'react'
import { ReferenceDataContext, type ReferenceDataValue } from './referenceDataContext'

export function useReferenceData(): ReferenceDataValue {
  const value = useContext(ReferenceDataContext)
  if (!value) {
    throw new Error('useReferenceData must be used within ReferenceDataProvider.')
  }
  return value
}
