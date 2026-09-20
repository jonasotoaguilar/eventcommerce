import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/session";
import { Layout } from "./components/Layout";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";

/**
 * U1 route map: public home plus auth pages. U2/U3 add shopper routes
 * (/catalog, /cart, /checkout, /orders/:id) behind <ProtectedRoute>.
 */
export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Layout>
          <Routes>
            <Route path="/" element={<HomePage />} />
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
