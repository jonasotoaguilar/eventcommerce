import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/session";
import { Layout } from "./components/Layout";
import { CartPage } from "./pages/CartPage";
import { CatalogPage } from "./pages/CatalogPage";
import { CheckoutPage } from "./pages/CheckoutPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { OrderTrackingPage } from "./pages/OrderTrackingPage";
import { ProductDetailPage } from "./pages/ProductDetailPage";
import { RegisterPage } from "./pages/RegisterPage";
import { ProtectedRoute } from "./routes/ProtectedRoute";

/**
 * U3 route map: public home, catalog browse/detail, and auth pages;
 * cart, checkout, and order tracking stay authenticated behind
 * <ProtectedRoute>.
 */
export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Layout>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/catalog" element={<CatalogPage />} />
            <Route path="/catalog/:id" element={<ProductDetailPage />} />
            <Route
              path="/cart"
              element={
                <ProtectedRoute>
                  <CartPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/checkout"
              element={
                <ProtectedRoute>
                  <CheckoutPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/orders/:id"
              element={
                <ProtectedRoute>
                  <OrderTrackingPage />
                </ProtectedRoute>
              }
            />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </Layout>
      </AuthProvider>
    </BrowserRouter>
  );
}

function NotFoundPage() {
  return (
    <section aria-labelledby="not-found-title">
      <h1 id="not-found-title">Page not found</h1>
      <p>The page you asked for does not exist.</p>
    </section>
  );
}
