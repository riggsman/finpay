import { Navigate, Route, Routes } from "react-router-dom";
import Landing from "./pages/Landing";
import Register from "./pages/Register";
import Login from "./pages/Login";
import ForgotPassword from "./pages/ForgotPassword";
import Dashboard from "./pages/Dashboard";
import Services from "./pages/Services";
import Electricity from "./pages/Electricity";
import Topup from "./pages/Topup";
import WalletAction from "./pages/WalletAction";
import Security from "./pages/Security";
import History from "./pages/History";
import TransactionDetail from "./pages/TransactionDetail";
import Kyc from "./pages/Kyc";
import Support from "./pages/Support";
import TicketDetail from "./pages/TicketDetail";
import Requests from "./pages/Requests";
import ProtectedRoute from "./routes/ProtectedRoute";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/register" element={<Register />} />
      <Route path="/login" element={<Login />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <Dashboard />
          </ProtectedRoute>
        }
      />
      <Route
        path="/services"
        element={
          <ProtectedRoute>
            <Services />
          </ProtectedRoute>
        }
      />
      <Route
        path="/services/electricity"
        element={
          <ProtectedRoute>
            <Electricity />
          </ProtectedRoute>
        }
      />
      <Route
        path="/services/airtime"
        element={
          <ProtectedRoute>
            <Topup category="airtime" />
          </ProtectedRoute>
        }
      />
      <Route
        path="/services/data"
        element={
          <ProtectedRoute>
            <Topup category="data" />
          </ProtectedRoute>
        }
      />
      <Route
        path="/wallet/send"
        element={
          <ProtectedRoute>
            <WalletAction mode="send" />
          </ProtectedRoute>
        }
      />
      <Route
        path="/wallet/withdraw"
        element={
          <ProtectedRoute>
            <WalletAction mode="withdraw" />
          </ProtectedRoute>
        }
      />
      <Route
        path="/wallet/requests"
        element={
          <ProtectedRoute>
            <Requests />
          </ProtectedRoute>
        }
      />
      <Route
        path="/security"
        element={
          <ProtectedRoute>
            <Security />
          </ProtectedRoute>
        }
      />
      <Route
        path="/transactions"
        element={
          <ProtectedRoute>
            <History />
          </ProtectedRoute>
        }
      />
      <Route
        path="/transactions/:id"
        element={
          <ProtectedRoute>
            <TransactionDetail />
          </ProtectedRoute>
        }
      />
      <Route
        path="/kyc"
        element={
          <ProtectedRoute>
            <Kyc />
          </ProtectedRoute>
        }
      />
      <Route
        path="/support"
        element={
          <ProtectedRoute>
            <Support />
          </ProtectedRoute>
        }
      />
      <Route
        path="/support/tickets/:id"
        element={
          <ProtectedRoute>
            <TicketDetail />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
