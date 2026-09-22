import { createContext } from 'react'
import type { Customer, Product, Supplier } from './types'

export type IdMap<T> = Record<number, T>

export type ReferenceDataValue = {
  loading: boolean
  error: string | null
  suppliers: Supplier[]
  products: Product[]
  customers: Customer[]
  supplierById: IdMap<Supplier>
  productById: IdMap<Product>
  customerById: IdMap<Customer>
  supplierName: (supplierId: number) => string
  productName: (productId: number) => string
  customerName: (customerId: number) => string
  refresh: () => void
}

export const ReferenceDataContext = createContext<ReferenceDataValue | null>(null)

export function toIdMap<T extends { id: number }>(rows: T[]): IdMap<T> {
  const mapped: IdMap<T> = {}
  if (!Array.isArray(rows)) {
    return mapped
  }
  for (const row of rows) {
    mapped[row.id] = row
  }
  return mapped
}
