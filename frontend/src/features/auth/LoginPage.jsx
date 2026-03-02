
import { useState } from "react";
import Header from "../../ui/Header";
import BrandLogo from "../../ui/BrandLogo";
import Input from "../../ui/Input";
import Button from "../../ui/Button";
import Card from "../../ui/Card";
import "../../styles.css";

export default function LoginPage({ onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    onLogin(email, password);
  };

  return (
    <>
      <Header title="Inloggen" />

      <div className="login-container">
        <Card className="login-card">
          <div style={{ display: "flex", justifyContent: "center", marginBottom: "24px" }}>
            <BrandLogo />
          </div>

          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: "16px" }}>
              <label>E-mail</label>
              <Input value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>

            <div style={{ marginBottom: "24px" }}>
              <label>Wachtwoord</label>
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </div>

            <div style={{ display: "flex", justifyContent: "center" }}>
              <Button type="submit">Inloggen</Button>
            </div>
          </form>
        </Card>
      </div>
    </>
  );
}
