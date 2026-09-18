import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { ReferenceDataProvider } from './api/referenceData'
import { AppLayout } from './layout/AppLayout'
import { CataloguePage } from './pages/CataloguePage'
import { CustomersPage } from './pages/CustomersPage'
import { DashboardPage } from './pages/DashboardPage'
import { EnquiriesPage } from './pages/EnquiriesPage'
import { InsightsPage } from './pages/InsightsPage'
import { InventoryPage } from './pages/InventoryPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { PreorderDetailPage } from './pages/PreorderDetailPage'
import { PreordersPage } from './pages/PreordersPage'
import { SupplierOrderDetailPage } from './pages/SupplierOrderDetailPage'
import { SupplierOrdersPage } from './pages/SupplierOrdersPage'

export default function App() {
  return (
    <BrowserRouter>
      <ReferenceDataProvider>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<DashboardPage />} />
            <Route path="enquiries" element={<EnquiriesPage />} />
            <Route path="preorders" element={<PreordersPage />} />
            <Route path="preorders/:id" element={<PreorderDetailPage />} />
            <Route path="supplier-orders" element={<SupplierOrdersPage />} />
            <Route path="supplier-orders/:id" element={<SupplierOrderDetailPage />} />
            <Route path="catalogue" element={<CataloguePage />} />
            <Route path="inventory" element={<InventoryPage />} />
            <Route path="customers" element={<CustomersPage />} />
            <Route path="insights" element={<InsightsPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </ReferenceDataProvider>
    </BrowserRouter>
  )
}
