import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { ApiError } from './client'
import { getCustomers, getProducts, getSuppliers } from './resources'
import { ReferenceDataContext, toIdMap, type ReferenceDataValue } from './referenceDataContext'
import type { Customer, Product, Supplier } from './types'

export function ReferenceDataProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const [customers, setCustomers] = useState<Customer[]>([])
  const [tick, setTick] = useState(0)

  const refresh = useCallback(() => {
    setError(null)
    setLoading(true)
    setTick((value) => value + 1)
  }, [])

  useEffect(() => {
    let cancelled = false
    Promise.all([getSuppliers(), getProducts(), getCustomers()])
      .then(([nextSuppliers, nextProducts, nextCustomers]) => {
        if (cancelled) {
          return
        }
        setSuppliers(nextSuppliers)
        setProducts(nextProducts)
        setCustomers(nextCustomers)
        setError(null)
      })
      .catch((caught: unknown) => {
        if (cancelled) {
          return
        }
        const message =
          caught instanceof ApiError ? caught.message : 'Reference data could not be loaded.'
        setError(message)
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [tick])

  const value = useMemo<ReferenceDataValue>(() => {
    const supplierById = toIdMap(suppliers)
    const productById = toIdMap(products)
    const customerById = toIdMap(customers)
    return {
      loading,
      error,
      suppliers,
      products,
      customers,
      supplierById,
      productById,
      customerById,
      supplierName: (supplierId) => supplierById[supplierId]?.name ?? `Supplier #${supplierId}`,
      productName: (productId) => productById[productId]?.name ?? `Product #${productId}`,
      customerName: (customerId) => customerById[customerId]?.name ?? `Customer #${customerId}`,
      refresh,
    }
  }, [customers, error, loading, products, refresh, suppliers])

  return (
    <ReferenceDataContext.Provider value={value}>{children}</ReferenceDataContext.Provider>
  )
}
