import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { ApiError } from './client'
import { getCustomers, getProducts, getSuppliers } from './resources'
import { ReferenceDataContext, toIdMap, type ReferenceDataValue } from './referenceDataContext'
import type { Customer, Product, Supplier } from './types'

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      reject(new ApiError('The request timed out.', 0))
    }, ms)
    promise.then(
      (value) => {
        window.clearTimeout(timer)
        resolve(value)
      },
      (caught: unknown) => {
        window.clearTimeout(timer)
        reject(caught)
      },
    )
  })
}

function settledValue<T>(result: PromiseSettledResult<T>, fallback: T): T {
  return result.status === 'fulfilled' ? result.value : fallback
}

function settledError(result: PromiseSettledResult<unknown>): string | null {
  if (result.status !== 'rejected') {
    return null
  }
  const reason = result.reason
  if (reason instanceof ApiError) {
    return reason.message
  }
  return 'Reference data could not be loaded.'
}

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
    Promise.allSettled([
      withTimeout(getSuppliers(), 20000),
      withTimeout(getProducts(), 20000),
      withTimeout(getCustomers(), 20000),
    ]).then(([nextSuppliers, nextProducts, nextCustomers]) => {
      if (cancelled) {
        return
      }
      setSuppliers(settledValue(nextSuppliers, []))
      setProducts(settledValue(nextProducts, []))
      setCustomers(settledValue(nextCustomers, []))
      const failures = [nextSuppliers, nextProducts, nextCustomers]
        .map(settledError)
        .filter((message): message is string => Boolean(message))
      setError(failures.length === 3 ? failures[0] : null)
      setLoading(false)
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
